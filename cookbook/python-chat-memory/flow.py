from nodes import answer_question, archive_memory, read_question, retrieve_memory
from sley import Flow

read_question.link(retrieve_memory, "retrieve")
retrieve_memory.link(answer_question, "answer")
answer_question.link(read_question, "continue")
answer_question.link(archive_memory, "archive")
archive_memory.link(read_question, "continue")

chat_flow = Flow(read_question)
