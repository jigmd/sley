---
complexity: 9
---

# Retrieval-Augmented Generation

This example separates document indexing from question answering with two Sley
Flows.

The offline Flow emits one branch per source text. Each branch chunks and embeds
its text, then calls `end(document)`. A `combine=` callback flattens the terminal
outputs and builds one in-memory index. The online Flow embeds a question, retrieves
the nearest chunk, and asks the model to answer only from that context.

```text
offline: dispatch -> (chunk -> embed -> end) x N -> combine -> build index
online:  embed query -> retrieve nearest chunk -> answer
```

The bundled corpus mixes one short Sley note with clearly marked fictional
samples. It exists to make retrieval observable, not to serve as a factual
knowledge base. This compact example uses one nearest neighbor; a real system
would preserve source metadata, retrieve several candidates, calibrate an
abstention threshold, and evaluate answers against a held-out question set.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py "How do I install Sley?"
```

Set `OPENAI_MODEL` or `OPENAI_EMBEDDING_MODEL` to override either provider
model. Squared-distance search is a few ordinary Python lines so the retrieval
step stays visible; a vector database is not needed for the lesson.
