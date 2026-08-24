---
complexity: 2.5
---

# Sley Hello World

Your first Sley application! This simple example demonstrates how to create a basic Sley app from scratch.

## Run

Set `OPENAI_API_KEY`, then run:

```bash
pip install -r requirements.txt
python main.py
```

## Project Structure

```
.
├── docs/          # Documentation files
├── utils/         # Utility functions
├── flow.py        # Sley implementation
├── main.py        # Main application entry point
├── models.py      # Optional state typing
└── README.md      # Project documentation
```

## What This Example Demonstrates

- Turn an ordinary function into a node with `@node`
- Read and write the run's state through `context.state`
- Finish an ordinary leaf by emitting nothing

The `answer` handler has no outgoing link and makes no control call. Its normal
return exits the Flow. Most leaf nodes do not need `context.end()`.

This is the typed example in this group. Its single state definition lives in
`models.py`, which can be skipped when focusing on the workflow.

## Additional Resources

- [Sley Documentation](https://github.com/jigmd/sley/tree/main/docs)
