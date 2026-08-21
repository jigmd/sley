from caskada import Context, Failure, Flow, RetryPolicy, node
from models import SummaryState
from utils.call_llm import call_llm


def summarize(context: Context[SummaryState]) -> None:
    text = context.state["data"]
    if not text:
        context.state["summary"] = "Empty text"
        return

    prompt = f"Summarize this text in 10 words: {text}"
    context.state["summary"] = call_llm(prompt)


def use_fallback(context: Context[SummaryState], _failure: Failure) -> None:
    context.state["summary"] = "There was an error processing your request."
    # An emission tells Caskada that recovery handled the failure.
    context.emit()


summarize_node = node(
    summarize,
    retry=RetryPolicy(max_attempts=3),
    recover=use_fallback,
)
flow = Flow(summarize_node)
