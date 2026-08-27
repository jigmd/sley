---
complexity: 4
---

# Stream an LLM Response

One Sley node prints an OpenAI stream as chunks arrive. The provider iterator
and Ctrl+C interruption stay inside the handler; the Flow remains a normal
one-node workflow.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```

Press Ctrl+C while text is streaming to stop reading further chunks. A normal
completed response exits immediately; there is no background input thread to
keep the process alive.
