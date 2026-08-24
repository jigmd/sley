---
complexity: 7
---

# Multi-Agent Taboo Game

Two independent Flows run concurrently. The hinter and guesser each have a
named self-link for their next turn, while two injected `asyncio.Queue` objects
carry messages between the runs.

Sley shallow-copies the top-level state for each run. Nested values are borrowed,
so both runs deliberately receive the same queues and `past_guesses` list. This
is application-managed communication, not shared Sley scheduler state.

When the guess is correct, both handlers return without emitting. Their Flows
then finish normally.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```
