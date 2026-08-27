---
complexity: 9
---

# Blind Best-of-N Judge

A dispatcher asks independent workers for materially different candidates. Once
every candidate settles, a judge compares anonymous pairs in randomized order
and advances the winner through a tournament. A final editor starts from the
winning candidate and adds only useful elements identified from losing entries.

```text
dispatch --> generate --end(candidate)
       \---- combine --> blind tournament --> editor
```

This differs from majority voting: candidates need not converge on one exact
answer. Pairwise comparison gives the judge a smaller decision than assigning
reliable absolute scores, while anonymous labels and randomized order reduce
position and self-preference cues.

The judge receives no candidate names, build rationale, or previous verdicts.
Each comparison is a separate stateless model request. Sley coordinates the
candidate fan-out and join; the local tournament remains ordinary application
code inside one meaningful selection step.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```
