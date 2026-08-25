---
description: Turn the release checks into a reusable quality gate with its own boundary and exit contract.
---

# Nested Flows

You already nested one Flow in the previous lesson: the release graph ran the
checks Flow as one element. It solved fan-out and fan-in, but the parent decision
still knew how to interpret a failed check.

This chapter adds the part that makes a nested Flow a useful public boundary.
We will wrap the checks in a quality gate that owns that policy and exposes only
two outcomes: normal completion or `blocked`.

Nothing else changes. Preparation still creates the slug. Passed work still
reaches the risk decision. Publishing and review still receive their branch
payloads.

## Give the child a public exit

After the checks combine, one decision turns their shared result into the
quality gate's small contract:

{% tabs %}
{% tab title="Python" %}

```python
@node
def quality_decision(context):
    if not context.state["checks_passed"]:
        context.emit("blocked", {"owner": "release team", "reason": "a required check failed"})


checks.link(quality_decision)
quality_gate = Flow(checks, name="quality gate", exits=("blocked",))
quality_gate.link(decide)
quality_gate.link(review, "blocked")
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
const qualityDecision = node<State>((context) => {
  if (!context.state.checksPassed) {
    context.emit('blocked', {
      owner: 'release team',
      reason: 'a required check failed',
    })
  }
})

checks.link(qualityDecision)
const qualityGate = new Flow(checks, {
  name: 'quality gate',
  exits: ['blocked'],
})
qualityGate.link(decide)
qualityGate.link(review, 'blocked')
```

{% endtab %}
{% endtabs %}

When checks pass, `quality_decision` makes no control call. Its implicit
unlabelled continuation has no internal link, so it leaves `quality_gate`
normally and follows the Flow element's unlabelled link to `decide`.

When checks fail, `quality_decision` emits `blocked`. There is no internal link
with that name, but the Flow declares it as an exit. The action crosses the
boundary and follows the `blocked` link on the Flow element to `review`.

An undeclared action with no internal link fails as `unknown_action`. The child
cannot accidentally leak a misspelling into its parent.

## Keep Exit and End distinct

An exit says: “this branch finished the child Flow; let the parent decide what
happens next.” A hard End says: “this branch is terminal.”

`context.end(value)` bypasses links and remains terminal across enclosing Flow
boundaries unless a combiner replaces it. The worker Ends inside the checks Flow
stay local because `collect` replaces them with one continuation to
`quality_decision`.

## Run the complete quality gate

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


async def main():
    cases = (
        (
            "passed",
            "low",
            [
                {"name": "tests", "passed": True},
                {"name": "security", "passed": True},
            ],
        ),
        (
            "failed",
            "low",
            [
                {"name": "tests", "passed": True},
                {"name": "security", "passed": False},
            ],
        ),
        (
            "high risk",
            "high",
            [
                {"name": "tests", "passed": True},
                {"name": "security", "passed": True},
            ],
        ),
    )
    for label, risk, required_checks in cases:
        state = await release.run(
            {"title": "Hello Sley", "risk": risk, "checks": required_checks}
        )
        print(f"{label}: {state['status']}")


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

const cases: Array<{ label: string; risk: State['risk']; checks: Check[] }> = [
  {
    label: 'passed',
    risk: 'low',
    checks: [
      { name: 'tests', passed: true },
      { name: 'security', passed: true },
    ],
  },
  {
    label: 'failed',
    risk: 'low',
    checks: [
      { name: 'tests', passed: true },
      { name: 'security', passed: false },
    ],
  },
  {
    label: 'high risk',
    risk: 'high',
    checks: [
      { name: 'tests', passed: true },
      { name: 'security', passed: true },
    ],
  },
]

for (const example of cases) {
  const state = await release.run({
    title: 'Hello Sley',
    risk: example.risk,
    checks: example.checks,
  })
  console.log(`${example.label}: ${state.status}`)
}
```

{% endtab %}
{% endtabs %}

The output is:

```text
passed: published: hello-sley to stable
failed: hello-sley: release team reviews because a required check failed
high risk: hello-sley: release team reviews because risk is high
```

The inner checks Flow still owns fan-out and combine. The new quality gate owns
the meaning of those results. The parent release graph no longer needs to know
why a check failed or how many checks ran.

## Nest around owned behavior

Create a nested Flow when the subgraph owns something readers can name:

- a public exit contract;
- a fan-in combiner;
- recovery for the whole scope;
- a local concurrency or activation limit;
- a reusable workflow boundary.

Do not nest merely because nodes live in the same directory. A boundary that
owns no behavior makes the graph harder to traverse without making it safer or
clearer.

## Change one thing

Add an internal `blocked` link from `quality_decision` to a new `remediate`
node. Predict whether the action still reaches the parent. Then remove that
internal link and watch the declared exit become active again. A physical link
wins before a Flow exit with the same name.

You have evolved a batch into a named boundary without rewriting its workers or
its parent routes. [Failures and results](failures-and-results.md) keeps this
same graph and adds a publishing failure at the smallest responsible node.
