from nodes import process, review, show_result
from sley import Flow

# A successful process call emits nothing, so it follows this unlabelled link.
process.link(review)
review.link(show_result, "approved")
review.link(process, "rejected")

feedback_flow = Flow(process, max_activations=20)


def create_feedback_flow() -> Flow:
    return feedback_flow
