---
description: Add independent checks to the release graph, publish one result per branch, and join them exactly once.
---

# Fan-out, End, and Combine

The release graph can prepare, decide, publish, and request review. Now it needs
tests and security checks before the decision. These checks are independent,
but the release must wait for all of them.

We will insert one checks Flow between `prepare` and `decide`. Everything you
already built stays in place.

A structured fan-out has four steps:

1. dispatch one branch for each item;
2. let each branch publish a completed value;
3. let the Flow wait until every branch settles;
4. combine the values once and continue.

## Several emissions create several branches

The dispatcher records one branch for every check:

```python
def dispatch(context):
    for check in context.state["checks"]:
        context.emit("run", check)
```

Each `emit("run", check)` carries a different `context.input` to the same
worker. Sley commits the complete buffer only after the dispatcher returns
normally. If dispatch fails, none of its recorded branches start.

## End publishes one branch result

The worker finishes its branch with a value for the join:

```python
def run_check(context):
    check = context.input
    context.end({"name": check["name"], "passed": check["passed"]})
```

`end(value)` creates a hard terminal for this branch, bypasses its links, and
contributes one output to the checks Flow. Sibling branches continue.

`end()` does not return from the function. Use a normal `return` when later code
must not run. `end()` carries no output; `end(None)` or `end(undefined)` carries
an explicit output whose value is `None` or `undefined`.

## Combine runs once after settlement

The checks Flow waits for every worker, then calls its combiner once:

```python
def collect(context, result):
    outcomes = list(result.outputs)
    context.state["checks_passed"] = all(item["passed"] for item in outcomes)
    context.emit()
```

`result.outputs` contains values from output-bearing terminals in settlement
order. It never contains shared state, handler return values, or intermediate
emissions. The combiner's single `emit()` replaces the worker terminals with
one continuation from the checks Flow to `decide`.

This example uses the default concurrency of one, so its workers run
sequentially. The [Concurrency and cycles](../guides/concurrency-and-cycles.md)
guide shows how to opt into parallel execution. With concurrent workers, carry
an index and sort when source order matters.

{% hint style="warning" %}
A node handler with zero control calls gets one implicit unlabelled
continuation. An empty dispatch loop therefore does not mean zero branches. If
an empty batch should finish without output, call `end()` and return.
{% endhint %}

## Run the evolved graph

The complete program inserts the checks Flow between `prepare` and `decide`.
The existing release decision and its branch payloads do not change.

{% tabs %}
{% tab title="Python" %}

```python
import asyncio

from sley import Flow, node


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
def decide(context):
    if not context.state["checks_passed"]:
        context.emit(
            "needs_review",
            {"owner": "release team", "reason": "a required check failed"},
        )
    elif context.state["risk"] == "high":
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
    context.state["status"] = (
        f"published: {context.state['slug']} to {context.input['channel']}"
    )


dispatch_node = node(dispatch)
run_check_node = node(run_check)
checks = Flow(dispatch_node, name="checks", combine=collect)

prepare.link(checks)
dispatch_node.link(run_check_node, "run")
checks.link(decide)
decide.link(review, "needs_review")
decide.link(publish, "ready")
release = Flow(prepare)


async def main():
    state = await release.run(
        {
            "title": "Hello Sley",
            "risk": "low",
            "checks": [
                {"name": "tests", "passed": True},
                {"name": "security", "passed": True},
            ],
        }
    )
    print(state["check_report"])
    print(state["status"])


asyncio.run(main())
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
import { Flow, node } from '@jigging/sley'

interface Check {
  name: string
  passed: boolean
}

interface State {
  title: string
  risk: 'low' | 'high'
  checks: Check[]
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

const decide = node<State>((context) => {
  if (!context.state.checksPassed) {
    context.emit('needs_review', {
      owner: 'release team',
      reason: 'a required check failed',
    })
  } else if (context.state.risk === 'high') {
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
  context.state.status = `published: ${context.state.slug} to ${context.input.channel}`
})

prepare.link(checks)
dispatch.link(runCheck, 'run')
checks.link(decide)
decide.link(review, 'needs_review')
decide.link(publish, 'ready')
const release = new Flow(prepare)

const state = await release.run({
  title: 'Hello Sley',
  risk: 'low',
  checks: [
    { name: 'tests', passed: true },
    { name: 'security', passed: true },
  ],
})
console.log(state.checkReport)
console.log(state.status)
```

{% endtab %}
{% endtabs %}

Both programs print:

```text
tests: passed, security: passed
published: hello-sley to stable
```

The whole release now reads:

```text
prepare -> checks -> decide -> publish or review
```

The checks Flow owns the synchronization problem. Its workers publish results
without racing on a shared list, and the release decision still runs exactly
once.

## Change one thing

Make the security check fail and predict the final route. Then raise the risk
while both checks pass. The same `decide` node should explain why each release
reaches review.

You have inserted dynamic branch work without discarding the graph you already
understood. [Nested Flows](nested-flows.md) turns those checks into a quality
gate with a small public exit contract.
