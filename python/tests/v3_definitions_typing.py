from typing import TypedDict, assert_type

from caskada import CompiledFlow, Context, Flow, Node, node


class StateA(TypedDict, total=False):
    value: str


class StateB(TypedDict, total=False):
    count: int


class JobInput(TypedDict):
    job: str


def source_handler(context: Context[StateA]) -> None:
    context.state["value"] = "ready"


def target_handler(context: Context[StateA, JobInput]) -> None:
    context.state["value"] = context.input["job"]


source = node(source_handler)
target = node(target_handler)
assert_type(source, Node[StateA])
assert_type(target, Node[StateA])
source.link(target)
source.link(target, "job")
compiled: CompiledFlow[StateA] = Flow(source).compile()
compiled.describe()


def wrong_handler(context: Context[StateB]) -> None:
    context.state["count"] = 1


wrong_state = node(wrong_handler)
source.link(wrong_state)  # type: ignore[arg-type]
Flow[StateA](wrong_state)  # type: ignore[arg-type]
Node()  # type: ignore[call-arg]
CompiledFlow()  # type: ignore[call-arg]
