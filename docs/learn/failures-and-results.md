---
description: Add publishing failure to the release graph, use final state normally, and keep structured evidence for diagnosis.
---

# Failures and Results

The release graph now owns preparation, checks, a quality boundary, risk
routing, publishing, and review. We will not replace it with a toy failure.
Instead, the existing `publish` node will simulate failure at the service
boundary it owns.

Only two things change: `publish` can raise, and the caller chooses how much
result detail it wants. The `service_available` / `serviceAvailable` boolean
below simulates the release service so the example stays provider-free.

## Make failure belong to the operation

The publishing node owns the publishing operation, so it also owns the
immediate failure:

{% tabs %}
{% tab title="Python" %}

```python
@node
def publish(context):
    if not context.state["service_available"]:
        raise ConnectionError("release service unavailable")
    context.state["status"] = f"published: {context.state['slug']}"
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
const publish = node<State>((context) => {
  if (!context.state.serviceAvailable) {
    throw new Error('release service unavailable')
  }
  context.state.status = `published: ${context.state.slug}`
})
```

{% endtab %}
{% endtabs %}

No catch belongs inside the node until the application has a meaningful local
fallback. An unavailable service stops this run instead of pretending the
release published.

## Use `run()` for the answer

`await flow.run(initial_state)` waits for completion and returns the run-owned
shared state. If the graph fails, it raises or rejects with `RunError`:

{% tabs %}
{% tab title="Python" %}

```python
try:
    state = await release.run(initial_state)
except RunError as error:
    print(error.result.failure.kind)
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
try {
  const state = await release.run(initialState)
} catch (error) {
  if (!(error instanceof RunError)) throw error
  console.log(error.result.failure.kind)
}
```

{% endtab %}
{% endtabs %}

The error keeps the exact failed result in `error.result`. Its normal
host-language cause points to the controlling application error when one
exists. This is the right boundary for most application calls.

## Use `start()` for the evidence

`flow.start(initial_state)` returns a `RunHandle`. Awaiting `handle.result()`
represents normal completion and failures captured by Sley as structured values:

```text
Completed { status, state, terminals }
Failed    { status, state, terminals, failure }
```

A terminal records how one branch settled, whether it carried output, its
settlement sequence, and the activation that produced it. A failed result keeps
terminals from sibling work that settled before failure.

`Failure.kind` identifies the runtime stage, such as `handler`,
`unknown_action`, or `activation_limit`. `cause` keeps the application error.
IDs and the `previous` link preserve failure history without asking you to parse
message text.

Native cancellation and failures outside Sley's workflow-failure contract may
still escape. A result handle replaces `RunError`; it is not a universal catch.

## Run the complete release graph

The full program keeps every earlier topology decision and exercises one
successful call plus both failure-reading APIs.

{% tabs %}
{% tab title="Python" %}

```python
import asyncio

from sley import Flow, RunError, node


@node
def prepare(context):
    context.state["slug"] = context.state["title"].strip().lower().replace(" ", "-")


def dispatch(context):
    for check in context.state["checks"]:
        context.emit("run", check)


def run_check(context):
    check = context.input
    context.end({"name": check["name"], "passed": check["passed"]})


def collect(context, result):
    outcomes = list(result.outputs)
    context.state["check_report"] = ", ".join(
        f"{item['name']}: {'passed' if item['passed'] else 'failed'}"
        for item in outcomes
    )
    context.state["checks_passed"] = all(item["passed"] for item in outcomes)
    context.emit()


@node
def quality_decision(context):
    if not context.state["checks_passed"]:
        context.emit(
            "blocked",
            {"owner": "release team", "reason": "a required check failed"},
        )


@node
def decide(context):
    if context.state["risk"] == "high":
        context.emit(
            "needs_review",
            {"owner": "release team", "reason": "risk is high"},
        )
    else:
        context.emit("ready", {"channel": "stable"})


@node
def review(context):
    request = context.input
    context.state["status"] = (
        f"{context.state['slug']}: {request['owner']} reviews because {request['reason']}"
    )


@node
def publish(context):
    if not context.state["service_available"]:
        raise ConnectionError("release service unavailable")
    context.state["status"] = (
        f"published: {context.state['slug']} to {context.input['channel']}"
    )


dispatch_node = node(dispatch)
run_check_node = node(run_check)
checks = Flow(dispatch_node, name="checks", combine=collect)
checks.link(quality_decision)
quality_gate = Flow(checks, name="quality gate", exits=("blocked",))

prepare.link(quality_gate)
dispatch_node.link(run_check_node, "run")
quality_gate.link(decide)
quality_gate.link(review, "blocked")
decide.link(review, "needs_review")
decide.link(publish, "ready")
release = Flow(prepare)


def initial_state(service_available):
    return {
        "title": "Hello Sley",
        "risk": "low",
        "checks": [
            {"name": "tests", "passed": True},
            {"name": "security", "passed": True},
        ],
        "service_available": service_available,
    }


async def main():
    state = await release.run(initial_state(True))
    print(state["status"])

    failed = await release.start(initial_state(False)).result()
    print(f"start: {failed.status}")
    if failed.status == "failed":
        print(f"kind: {failed.failure.kind}")

    try:
        await release.run(initial_state(False))
    except RunError as error:
        print(f"run error: {error.result.failure.kind}")


asyncio.run(main())
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
import { Flow, node, RunError } from '@jigging/sley'

interface Check {
  name: string
  passed: boolean
}

interface State {
  title: string
  risk: 'low' | 'high'
  checks: Check[]
  serviceAvailable: boolean
  slug?: string
  checkReport?: string
  checksPassed?: boolean
  status?: string
}

interface ReviewRequest {
  owner: string
  reason: string
}

interface PublishTarget {
  channel: string
}

const prepare = node<State>((context) => {
  context.state.slug = context.state.title.trim().toLowerCase().replaceAll(' ', '-')
})

const dispatch = node<State>((context) => {
  for (const check of context.state.checks) {
    context.emit('run', check)
  }
})

const runCheck = node<State, Check>((context) => {
  context.end({ name: context.input.name, passed: context.input.passed })
})

const checks = new Flow(dispatch, {
  name: 'checks',
  combine(context, result) {
    const outcomes = result.outputs.map((value) => value as Check)
    context.state.checkReport = outcomes.map((item) => `${item.name}: ${item.passed ? 'passed' : 'failed'}`).join(', ')
    context.state.checksPassed = outcomes.every((item) => item.passed)
    context.emit()
  },
})

const qualityDecision = node<State>((context) => {
  if (!context.state.checksPassed) {
    context.emit('blocked', {
      owner: 'release team',
      reason: 'a required check failed',
    })
  }
})
checks.link(qualityDecision)

const decide = node<State>((context) => {
  if (context.state.risk === 'high') {
    context.emit('needs_review', { owner: 'release team', reason: 'risk is high' })
  } else {
    context.emit('ready', { channel: 'stable' })
  }
})

const review = node<State, ReviewRequest>((context) => {
  const request = context.input
  context.state.status = `${context.state.slug}: ${request.owner} reviews because ${request.reason}`
})

const publish = node<State, PublishTarget>((context) => {
  if (!context.state.serviceAvailable) {
    throw new Error('release service unavailable')
  }
  context.state.status = `published: ${context.state.slug} to ${context.input.channel}`
})

const qualityGate = new Flow(checks, {
  name: 'quality gate',
  exits: ['blocked'],
})

prepare.link(qualityGate)
dispatch.link(runCheck, 'run')
qualityGate.link(decide)
qualityGate.link(review, 'blocked')
decide.link(review, 'needs_review')
decide.link(publish, 'ready')
const release = new Flow(prepare)

function initialState(serviceAvailable: boolean): State {
  return {
    title: 'Hello Sley',
    risk: 'low',
    checks: [
      { name: 'tests', passed: true },
      { name: 'security', passed: true },
    ],
    serviceAvailable,
  }
}

const state = await release.run(initialState(true))
console.log(state.status)

const failed = await release.start(initialState(false)).result()
console.log(`start: ${failed.status}`)
if (failed.status === 'failed') {
  console.log(`kind: ${failed.failure.kind}`)
}

try {
  await release.run(initialState(false))
} catch (error) {
  if (error instanceof RunError) {
    console.log(`run error: ${error.result.failure.kind}`)
  } else {
    throw error
  }
}
```

{% endtab %}
{% endtabs %}

Both programs print:

```text
published: hello-sley to stable
start: failed
kind: handler
run error: handler
```

The topology is unchanged from the nested-Flow lesson. The simulated publishing
operation failed at the node that owns it, and the rest of the graph stayed
understandable.

## Put failure policy where ownership lives

Retry belongs on the smallest node whose complete operation is safe to repeat.
Node recovery owns a local fallback. Flow recovery owns the failure of a whole
scope and can see sibling terminals that already settled.

That placement is graph design, not error-handler syntax. Put policy too high
and you repeat unrelated checks and decisions. Put it too low and the code lacks
the context to choose a meaningful fallback.

## Change one thing

Write one state field in `publish` before the exception and inspect the failed
result. Notice what Sley preserves and what it does not roll back. Then decide
whether retrying the complete handler would be safe.

You have now evolved one graph from a linear path through routing, branch data,
fan-out, fan-in, nested boundaries, and failure evidence. The final Learn
chapter, [Design graphs that stay clear](graph-design.md), turns that experience
into reusable judgment for your own systems.
