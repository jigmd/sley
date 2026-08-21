---
complexity: 4
---

# LLM Streaming and Interruption

One Caskada node prints an OpenAI stream while a small listener thread waits for
ENTER. The example keeps user-driven stream interruption inside the tool code;
the Flow itself remains a normal one-node workflow.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```

Press ENTER while text is streaming to stop reading further chunks.
