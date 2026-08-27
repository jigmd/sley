---
complexity: 15
---

# Reference-Grounded Quality Loop

This capstone composes the smaller orchestration patterns into one bounded
quality workflow. A checked-in benchmark names a narrow comparison slice,
freezes shared foundations, ranks the deciding dimensions, and defines
acceptance before any model call.

```text
set bar --> component Flow x N --> combine --> integrate --> whole judge
               ^      |                                  |          |
               |revise|                                  \--revise--/
               \------/                                  \--approved/stopped
```

Each component branch is its own evaluator–optimizer Flow. Builders receive the
same foundation but separate goals and reference slices. A fresh judge request
compares anonymous, randomly ordered artifacts; deterministic phrase checks run
alongside that model verdict. Only locally accepted components reach the
integration editor.

The assembled artifact then faces three blind comparisons. Two candidate wins
or ties reach the `"approved"` exit. The `"stopped"` exit records an unreachable
bar, a component or integration cap, or two consecutive passes with the same
material gap. Every cycle also has `max_activations` as a runtime backstop.

The local benchmark keeps the example reproducible. Replace it with a named,
licensed artifact and comparable slices in a real application. Model isolation,
artifact capture, cost budgets, persistence, and human escalation remain
application responsibilities.

This composition is often described as a
[Gauntlet Loop](https://somethingbig.ai/gauntlet-loop) or
[benchmark loop](https://github.com/martbln/benchmark-loop). Its useful parts
are the concrete feedback source, blind comparison, integration pass, and honest
stopping contract—not the branded name.

## Run

```bash
export OPENAI_API_KEY="your-api-key"
pip install -r requirements.txt
python main.py
```
