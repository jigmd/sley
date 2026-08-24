---
complexity: 4
---

# Streamlit Human Review

A small Streamlit application with three UI stages: submit, review, and
complete.

Streamlit owns the pause while a person reviews the output. Sley runs one
Flow to process the input and another after approval to finalize it. Each call
stores the state returned by `run()` back into `st.session_state`.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```
