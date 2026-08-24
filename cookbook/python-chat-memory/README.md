---
complexity: 7
---

# Chat with Memory Retrieval

A chat that keeps three recent conversation pairs and archives older pairs in a
vector index.

The current question travels through `context.input`. Conversation history and
the vector index live in `context.state` because every turn needs them. Once the
active history grows past three pairs, `answer_question` sends the oldest pair
to `archive_memory` before the next turn:

```python
context.emit("archive", oldest_pair)
```

Named links make the two possible paths visible: answer another question
directly, or archive a pair first.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```
