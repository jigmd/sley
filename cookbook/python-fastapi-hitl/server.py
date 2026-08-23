import asyncio
import json
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from flow import create_feedback_flow
from pydantic import BaseModel, Field

HERE = Path(__file__).parent
app = FastAPI(title="Sley Feedback Loop")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
tasks = {}


class SubmitRequest(BaseModel):
    data: str = Field(min_length=1)


class SubmitResponse(BaseModel):
    task_id: str
    message: str = "Task submitted"


class FeedbackRequest(BaseModel):
    feedback: str


async def run_flow_background(task_id: str) -> None:
    task = tasks[task_id]
    queue = task["queue"]
    await queue.put({"status": "running"})

    try:
        state = await create_feedback_flow().run(
            {
                "task_input": task["input"],
                "review": task["review"],
                "sse_queue": queue,
            }
        )
        task["state"] = state
        task["status"] = "completed"
        await queue.put({"status": "completed", "final_result": state["final_result"]})
    except Exception as error:  # noqa: BLE001 - translate task failure into SSE
        task["status"] = "failed"
        await queue.put({"status": "failed", "error": str(error)})
    finally:
        await queue.put(None)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def get_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post(
    "/submit", response_model=SubmitResponse, status_code=status.HTTP_202_ACCEPTED
)
async def submit_task(request: SubmitRequest, background: BackgroundTasks):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "input": request.data,
        "review": {"event": asyncio.Event(), "feedback": None},
        "queue": asyncio.Queue(),
        "status": "pending",
    }
    await tasks[task_id]["queue"].put({"status": "pending", "task_id": task_id})
    background.add_task(run_flow_background, task_id)
    return SubmitResponse(task_id=task_id)


@app.post("/feedback/{task_id}")
async def provide_feedback(task_id: str, request: FeedbackRequest):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    if request.feedback not in {"approved", "rejected"}:
        raise HTTPException(
            status_code=422, detail="Feedback must be approved or rejected"
        )

    task = tasks[task_id]
    channel = task["review"]
    if channel["event"].is_set():
        raise HTTPException(status_code=409, detail="Feedback already submitted")

    channel["feedback"] = request.feedback
    await task["queue"].put(
        {"status": "processing_feedback", "feedback_value": request.feedback}
    )
    channel["event"].set()
    return {"message": f"Feedback '{request.feedback}' received"}


@app.get("/stream/{task_id}")
async def stream_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    queue = tasks[task_id]["queue"]

    async def events():
        while True:
            update = await queue.get()
            if update is None:
                yield f"data: {json.dumps({'status': 'stream_closed'})}\n\n"
                return
            yield f"data: {json.dumps(update)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
