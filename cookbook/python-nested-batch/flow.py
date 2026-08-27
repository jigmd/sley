import os

from nodes import calculate_average, load_grades
from sley import Flow, node


def create_base_flow():
    load = node(load_grades)
    calculate = node(calculate_average)

    load.link(calculate, "calculate")
    return Flow(load)


def dispatch_class(context):
    class_name = context.input["item"]
    class_path = os.path.join("school", class_name)
    students = sorted(name for name in os.listdir(class_path) if name.endswith(".txt"))
    if not students:
        raise ValueError(f"class has no student grade files: {class_name}")

    print(f"Processing {class_name}...")
    # These branches belong to this class Flow, so it joins only this class's students.
    for student in students:
        context.emit(
            "student",
            {"class_name": class_name, "item": student},
        )


def class_reducer(context, result):
    class_name = context.input["item"]
    class_average = sum(student["average"] for student in result.outputs) / len(
        result.outputs
    )

    print(f"Class {class_name.split('_')[1].upper()} Average: {class_average:.2f}\n")
    # This class result becomes one output for the enclosing school Flow.
    context.end({"item": class_average})


def create_class_flow():
    dispatcher = node(dispatch_class)
    dispatcher.link(create_base_flow(), "student")

    return Flow(dispatcher, combine=class_reducer)


def dispatch_school(context):
    classes = sorted(
        name
        for name in os.listdir("school")
        if os.path.isdir(os.path.join("school", name))
    )
    if not classes:
        raise ValueError("school has no class directories")

    for class_name in classes:
        context.emit("class", {"item": class_name})


def school_reducer(context, result):
    school_average = sum(item["item"] for item in result.outputs) / len(result.outputs)
    print(f"School Average: {school_average:.2f}")
    # Emitting nothing preserves the class terminals after this final aggregation.


def create_school_flow():
    dispatcher = node(dispatch_school)
    dispatcher.link(create_class_flow(), "class")

    return Flow(dispatcher, combine=school_reducer)
