---
complexity: 9.5
---

# Nested Batch Flow Example

This example demonstrates nested batch Flows using a simple school grades
calculator.

## Run

```bash
pip install -r requirements.txt
python main.py
```

## What this Example Does

Calculates average grades for:

1. Each student in a class
2. Each class in the school

## Control and Data Flow

- Per-branch values move through `context.input`; completed branch results move
  through `end(value)` and `result.outputs`.
- Repeated `emit` calls fan out students and classes.
- Each student uses `end(value)` to give its result to the class `combine`; each
  class does the same for the school `combine`.
- The final combiner emits nothing, preserving the class terminals while
  `run()` returns the shared state.

## Structure

```
school/
├── class_a/
│   ├── student1.txt  (grades: 7.5, 8.0, 9.0)
│   └── student2.txt  (grades: 8.5, 7.0, 9.5)
└── class_b/
    ├── student3.txt  (grades: 6.5, 8.5, 7.0)
    └── student4.txt  (grades: 9.0, 9.5, 8.0)
```

## Expected Output

```
Processing school grades...

Processing class_a...
- student1.txt: Average = 8.2
- student2.txt: Average = 8.3
Class A Average: 8.25

Processing class_b...
- student3.txt: Average = 7.3
- student4.txt: Average = 8.8
Class B Average: 8.08

School Average: 8.17
```
