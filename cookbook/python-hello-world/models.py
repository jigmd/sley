from typing import TypedDict


class QuestionState(TypedDict):
    question: str
    answer: str | None
