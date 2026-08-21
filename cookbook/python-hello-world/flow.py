from caskada import Context, Flow, node
from models import QuestionState
from utils.call_llm import call_llm


# @node turns an ordinary Python function into a Caskada node.
@node
def answer(context: Context[QuestionState]) -> None:
    # Every node in this run can read and update context.state.
    context.state["answer"] = call_llm(context.state["question"])


# This Flow starts at answer; with no link, its normal return finishes the Flow.
qa_flow = Flow(answer)
