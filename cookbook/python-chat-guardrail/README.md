---
complexity: 5
---

# Travel Chat Guardrail

A travel assistant that validates each question before sending it to the main
chat model.

The guardrail routes valid questions to `answer_question` and invalid questions
back to `read_question`:

```python
validate_question.link(read_question, "retry")
validate_question.link(answer_question, "answer")
```

Each `emit()` carries control to one named link. Typing `exit` makes
`read_question` return without an emission, so that branch leaves the Flow and
the chat ends.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```
