---
complexity: 9
---

# Evaluator–Optimizer Supervisor

A builder drafts an incident update from supplied facts. A separate evaluator
compares the candidate with an explicit rubric and returns structured evidence
plus the smallest requested correction.

```text
candidate Flow --candidate--> evaluate --revise--> candidate Flow
                                      \--approved--> finish
                                      \--stopped----> finish
```

The candidate is a nested Flow with a declared `"candidate"` exit. The outer
Flow declares `"approved"` and `"stopped"` exits, so both successful acceptance
and an honest failure to reach the bar are visible outcomes. `max_activations`
backs up the application-level revision budget if the routing logic breaks.

The evaluator receives only the facts, rubric, and actual candidate. It does not
receive the builder's rationale. A `revise` verdict must include observable
evidence and a concrete requested change; explanations do not count as fixes.

This is the reusable graph underneath evaluator–optimizer, independent critic,
constitutional revision, and reviewer–reviser workflows. Change the evaluator
policy without changing the topology.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```
