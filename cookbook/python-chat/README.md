---
complexity: 3
---

# Simple Chat

A terminal chat built from one node and one named self-link:

```python
chat.link(chat, "continue")
```

Each turn appends messages to `context.state` and emits `"continue"`. Typing
`exit` returns without an emission, so the branch leaves the Flow and the chat
ends.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```
