---
machine-display: false
---

# Limits and Concurrency

Sley limits work inside each Flow. Provider quotas, request timeouts, and
limits shared across separate runs remain application concerns.

## Local Flow Concurrency

`Flow(..., concurrency=N)` limits the number of direct child activations that
one invocation of that Flow may run at once:

```python
workers = Flow(dispatch, concurrency=8, combine=collect)
```

```typescript
const workers = new Flow(dispatch, { concurrency: 8, combine: collect })
```

Several buffered `emit(...)` calls create branches. The owning Flow admits at
most `N` of its direct children concurrently. A nested Flow has its own local
cap; there is no hidden run-wide concurrency setting.

Concurrency does not make synchronous work nonblocking. Async handlers must
yield, and blocking clients need their own async API or deliberate thread or
process offload.

## Activation Limits

`max_activations` / `maxActivations` bounds direct activations inside each Flow
invocation. It is useful for deliberate cycles or dynamic fan-out:

```python
review = Flow(check, max_activations=20)
```

```typescript
const review = new Flow(check, { maxActivations: 20 })
```

Exhaustion fails the run with an `activation_limit` Failure. The count does not
include descendants inside a nested Flow or retry attempts.

## Shared Provider Limits

A Flow cap does not coordinate separate runs or requests issued outside that
scope. Put a shared semaphore or rate limiter in the injected service client
when several workflows share one provider:

```python
async def call_model(prompt):
    async with provider_limiter:
        return await client.generate(prompt, timeout=30)
```

Keep retry ownership clear. Use provider retries for transport behavior or node
retry for the whole handler operation. Stacking both can multiply attempts.

Start with concurrency 1. Raise a Flow's cap only when its branches are
independent and the downstream service can absorb the work.
