---
complexity: 6
---

# PDF Vision Batch

Convert every PDF page to an image and extract its text with OpenAI's vision
model.

`dispatch_pdfs` emits one branch input per file. Each `process_pdf` branch ends
with one file result. After every branch settles, the Flow's `combine` callback
collects `result.outputs` into the final run state.

This is the complete batch shape:

```text
dispatch_pdfs --process--> process_pdf --end(file_result)--> combine
```

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```
