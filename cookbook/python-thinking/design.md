# Iterative Plan Refinement Design

## Goal

Teach a bounded model-driven cycle without storing or displaying private
reasoning traces.

## Graph

```python
refine = node(refine_plan, retry=RetryPolicy(max_attempts=3, delay_ms=1_000))
refine.link(refine, "continue")
flow = Flow(refine, max_activations=4)
```

The model returns a concise progress summary, a flat plan, a routing decision,
and a final answer when complete. The handler validates that complete shape
before changing state or emitting control.

## State

```python
{
    "problem": str,
    "max_iterations": int,
    "iterations": list[dict],
    "solution": str | None,
}
```

The application iteration limit expresses domain policy. The Flow activation
limit remains an independent safety backstop for the cycle.
