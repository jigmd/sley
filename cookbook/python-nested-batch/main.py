import os

from flow import create_school_flow


def create_sample_data():
    os.makedirs("school/class_a", exist_ok=True)
    os.makedirs("school/class_b", exist_ok=True)

    data = {
        "class_a": {
            "student1.txt": [7.5, 8.0, 9.0],
            "student2.txt": [8.5, 7.0, 9.5],
        },
        "class_b": {
            "student3.txt": [6.5, 8.5, 7.0],
            "student4.txt": [9.0, 9.5, 8.0],
        },
    }

    for class_name, students in data.items():
        for student, grades in students.items():
            file_path = os.path.join("school", class_name, student)
            with open(file_path, "w") as grade_file:
                grade_file.writelines(f"{grade}\n" for grade in grades)


async def main():
    create_sample_data()

    print("Processing school grades...\n")
    await create_school_flow().run({})


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
