import logging
from collections.abc import AsyncIterable
from typing import ClassVar

import common.server.utils as server_utils
from common.server.task_manager import InMemoryTaskManager
from common.types import (
    Artifact,
    InternalError,
    InvalidParamsError,
    JSONRPCResponse,
    Message,
    SendTaskRequest,
    SendTaskResponse,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
    TaskSendParams,
    TaskState,
    TaskStatus,
    TextPart,
    UnsupportedOperationError,
)
from flow import agent_flow

logger = logging.getLogger(__name__)


class SleyTaskManager(InMemoryTaskManager):
    """Bridge between an A2A task and the Sley Flow."""

    SUPPORTED_CONTENT_TYPES: ClassVar[list[str]] = ["text", "text/plain"]

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        params = request.params
        if not server_utils.are_modalities_compatible(
            params.acceptedOutputModes, self.SUPPORTED_CONTENT_TYPES
        ):
            error = server_utils.new_incompatible_types_error(request.id).error
            return SendTaskResponse(id=request.id, error=error)

        await self.upsert_task(params)
        await self.update_store(
            params.id, TaskStatus(state=TaskState.WORKING), artifacts=[]
        )

        query = self._get_user_query(params)
        if query is None:
            message = Message(
                role="agent", parts=[TextPart(text="No text query found")]
            )
            await self.update_store(
                params.id,
                TaskStatus(state=TaskState.FAILED, message=message),
                artifacts=[],
            )
            return SendTaskResponse(
                id=request.id,
                error=InvalidParamsError(
                    message="No text query found in message parts"
                ),
            )

        try:
            # `run()` returns the invocation-owned final state; the request seed is
            # intentionally not used as an output channel.
            state = await agent_flow.run({"question": query})
            answer_text = state.get("answer", "Agent did not produce an answer.")
            task = await self.update_store(
                params.id,
                TaskStatus(state=TaskState.COMPLETED),
                [Artifact(parts=[TextPart(text=answer_text)])],
            )
            return SendTaskResponse(
                id=request.id,
                result=self.append_task_history(task, params.historyLength),
            )
        except Exception as error:
            logger.exception("Sley failed for task %s", params.id)
            message = Message(
                role="agent", parts=[TextPart(text=f"Agent execution failed: {error}")]
            )
            await self.update_store(
                params.id,
                TaskStatus(state=TaskState.FAILED, message=message),
                artifacts=[],
            )
            return SendTaskResponse(
                id=request.id, error=InternalError(message=f"Agent error: {error}")
            )

    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        return JSONRPCResponse(
            id=request.id,
            error=UnsupportedOperationError(message="Streaming not supported"),
        )

    @staticmethod
    def _get_user_query(params: TaskSendParams) -> str | None:
        for part in params.message.parts:
            if isinstance(part, TextPart):
                return part.text
        return None
