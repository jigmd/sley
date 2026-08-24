---
complexity: 13
---

# Research Supervisor

This project demonstrates a supervisor that oversees an unreliable [research agent](../python-agent) to ensure high-quality answers.

## Run

Set `OPENAI_API_KEY`, then run:

```bash
pip install -r requirements.txt
python main.py
```

## Features

- Evaluates responses for quality and relevance
- Rejects nonsensical or unreliable answers
- Requests new answers until a quality response is produced

## How It Works?

The magic happens through a simple but powerful graph structure with these main components:

```mermaid
graph TD
    subgraph InnerAgent[Inner Research Agent]
        DecideAction -->|"search"| SearchWeb
        DecideAction -->|"answer"| UnreliableAnswer
        SearchWeb -->|"decide"| DecideAction
    end

    InnerAgent --> Supervisor
    Supervisor -->|"retry"| InnerAgent
```

Here's what each part does:

1. **DecideAction**: Figures out whether to search or answer based on current context
2. **SearchWeb**: Finds information using web search
3. **UnreliableAnswer**: Generates answers (with a 50% chance of being unreliable)
4. **Supervisor**: Validates answers and rejects nonsensical ones

The answer function emits nothing, which exits the inner Flow and reaches the
supervisor. A rejection emits `"retry"` and re-enters that inner Flow. An
approval emits nothing, which exits the outer Flow and completes the run. This
is ordinary Flow termination, so the example needs neither `end()` nor
`combine()`.

## Example Output

```
🤔 Processing question: Who won the Nobel Prize in Physics 2024?
🤔 Agent deciding what to do next...
🔍 Agent decided to search for: Nobel Prize in Physics 2024 winner
🌐 Searching the web for: Nobel Prize in Physics 2024 winner
📚 Found information, analyzing results...
🤔 Agent deciding what to do next...
💡 Agent decided to answer the question
🤪 Generating unreliable dummy answer...
✅ Answer generated successfully
    🔍 Supervisor checking answer quality...
    ❌ Supervisor rejected answer: Answer appears to be nonsensical or unhelpful
🤔 Agent deciding what to do next...
💡 Agent decided to answer the question
✍️ Crafting final answer...
✅ Answer generated successfully
    🔍 Supervisor checking answer quality...
    ✅ Supervisor approved answer: Answer appears to be legitimate

🎯 Final Answer:
The Nobel Prize in Physics for 2024 was awarded jointly to John J. Hopfield and Geoffrey Hinton. They were recognized "for foundational discoveries and inventions that enable machine learning with artificial neural networks." Their work has been pivotal in the field of artificial intelligence, specifically in developing the theories and technologies that support machine learning using artificial neural networks. John Hopfield is associated with Princeton University, while Geoffrey Hinton is connected to the University of Toronto. Their achievements have laid essential groundwork for advancements in AI and its widespread application across various domains.
```

## Files

- [`main.py`](./main.py): The starting point - runs the whole show!
- [`flow.py`](./flow.py): Connects everything together into a smart agent with supervision
- [`nodes.py`](./nodes.py): The building blocks that make decisions, take actions, and validate answers
- [`utils.py`](./utils.py): Helper functions for talking to the LLM and searching the web
