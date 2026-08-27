import os


def load_grades(context):
    student = context.input
    path = os.path.join("school", student["class_name"], student["item"])

    with open(path) as grades_file:
        grades = [float(line.strip()) for line in grades_file]
    if not grades:
        raise ValueError(f"grade file is empty: {path}")

    context.emit("calculate", {**student, "grades": grades})


def calculate_average(context):
    student = context.input
    average = sum(student["grades"]) / len(student["grades"])

    print(f"- {student['item']}: Average = {average:.1f}")
    context.end({**student, "average": average})
