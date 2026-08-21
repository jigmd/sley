from caskada import Flow
from nodes import process, review, show_result

# A successful process call emits nothing, so it follows this unlabelled link.
process.link(review)
review.link(show_result, "approved")
review.link(process, "rejected")

feedback_flow = Flow(process)


def create_feedback_flow() -> Flow:
    return feedback_flow
