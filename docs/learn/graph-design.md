---
description: Design graph topology, data flow, joins, boundaries, cycles, and failures so the system stays understandable as it grows.
---

# Design Graphs That Stay Clear

You now know every mechanism in Sley's core model. The harder skill is deciding
when to use each one.

Good graph design is not about drawing more boxes. It is about making the
important transitions in a system obvious, keeping data ownership honest, and
placing boundaries where the right code has enough context to decide what
happens next.

This chapter is a design toolkit you can carry to any graph runtime.

## Start with the decisions, not the nodes

Before writing handlers, describe the workflow in domain language:

```text
prepare a release
if it is ready, publish it
if it needs review, wait for approval
run every required check
join the results before the final decision
```

The verbs suggest work. The “if” and “before” phrases reveal topology. Model the
few transitions that matter to the application; leave local implementation
detail as ordinary function calls inside a node.

A useful graph answers two questions at a glance:

1. What may happen next?
2. What must finish before something else may happen?

If the topology cannot answer those, adding more nodes will not help.

## Choose node boundaries by meaning

A node is a workflow boundary, not a line of code. Give it one responsibility
readers can name and one failure policy that makes sense for the whole handler.

| Smell                                  | Better question                                     |
| -------------------------------------- | --------------------------------------------------- |
| One node performs the whole workflow   | Which decisions deserve visible routes?             |
| Every helper function becomes a node   | Does this step matter to topology or policy?        |
| A node mutates many unrelated fields   | Is it hiding several outcomes behind one name?      |
| Retry would repeat unsafe side effects | Can the fallible operation become its own boundary? |
| Names describe implementation detail   | What domain event does this node represent?         |

The right size is usually the smallest unit that has a meaningful place in the
workflow, not the smallest unit that can be executed.

## Make the happy path quiet

Use the unlabelled link for the ordinary continuation. Use named actions for
real decisions:

```python
prepare.link(decide)
decide.link(publish, "ready")
decide.link(review, "needs_review")
```

This lets a reader scan the graph without translating labels such as `default`
or `next`. Prefer outcome names that remain meaningful if the target changes.

A decision node should enumerate its allowed answers. An unknown answer should
fail, because silent routing guesses turn domain mistakes into distant bugs.

## Give each value one role

Use data ownership to keep branches understandable:

- **State** holds facts the run shares.
- **Input** carries the item this branch is working on.
- **Terminal output** publishes completed branch work to a join.

When every branch writes into shared lists or counters, data flow becomes an
implicit second graph. Prefer branch input and terminal output until shared
state is genuinely the simpler expression.

Concurrent shared writes are ordinary concurrent programming. Sley cannot make
an ambiguous ownership model safe by scheduling it differently.

## Pair fan-out with an explicit join

Fan-out creates a question: who knows when all branches are done? The owning
Flow does. Put fan-in there with `combine` instead of recreating settlement with
an application counter.

Choose the join boundary around the set of work that must settle together. Too
wide, and unrelated work waits. Too narrow, and the parent still needs another
coordination mechanism.

Terminal settlement order is not source order under concurrency. Carry an
index when order belongs to the result; do not rely on scheduler timing.

## Nest around behavior, not organization

A nested Flow should make the parent graph smaller while giving the child real
ownership: exits, combine, recovery, concurrency, activation limits, or reuse.

If the only reason to nest is that several files share a folder, the boundary
adds navigation without a contract. If the parent can say “run the quality gate”
without knowing its internal checks, the boundary is doing useful work.

Treat a Flow exit as part of the child's public vocabulary. Keep that vocabulary
small and domain-specific.

## Make cycles prove they can stop

A loop needs both a domain exit and a runtime backstop:

{% tabs %}
{% tab title="Python" %}

```python
@node
def revise(context):
    context.state["revision"] += 1
    action = "approved" if context.state["revision"] >= 3 else "again"
    context.emit(action)


revise.link(revise, "again")
review = Flow(revise, exits=("approved",), max_activations=10)
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
const revise = node<{ revision: number }>((context) => {
  context.state.revision++
  const action = context.state.revision >= 3 ? 'approved' : 'again'
  context.emit(action)
})

revise.link(revise, 'again')
const review = new Flow(revise, {
  exits: ['approved'],
  maxActivations: 10,
})
```

{% endtab %}
{% endtabs %}

The `approved` route explains normal termination. The activation limit catches
a broken condition before the graph loops forever. A hidden default limit would
protect the runtime while obscuring the workflow's real contract, so Sley makes
the choice yours.

Ask of every cycle:

1. What changes on each pass?
2. What condition exits normally?
3. What bound catches a broken condition?
4. Is a loop clearer than a normal loop inside one node?

## Put failures at the smallest responsible boundary

Retry one handler only when its entire operation is safe to repeat. Recover at
the node when the fallback is local. Recover at the Flow when the decision needs
the outcome of the scope or its partial terminals.

Validation failures, programming errors, and unavailable services do not mean
the same thing. A mature graph names which failures are transient, which become
domain routes, and which must stop the run.

Avoid a universal catch-all recovery. It makes every failure look handled while
erasing the distinction the graph was meant to expose.

## Test decisions and boundaries

Graph tests should assert observable behavior, not imitate the scheduler.

Cover:

- the unlabelled path and every named decision;
- empty and multi-item fan-out;
- join behavior and ordering requirements;
- normal exit versus hard End;
- retry stopping and recovery replacement;
- cycle termination and its activation guard;
- state returned to the caller and structured failure evidence.

Test domain helpers directly as ordinary functions. Run a real small Flow when
the topology is what you need to prove.

## Review a graph before you ship it

Use this checklist in design review:

1. Can someone name the purpose of every node and nested Flow?
2. Are all meaningful decisions visible as links?
3. Does each value have an obvious owner: state, input, or output?
4. Does every fan-out have the right settlement boundary?
5. Does every cycle have a normal exit and explicit guard?
6. Is retry limited to safe, repeatable work?
7. Can failures surface without parsing logs or messages?
8. Could any node, edge, or scope be deleted without hiding behavior?

The last question matters most. A clear graph is not the graph with the most
structure. It is the smallest graph that makes the system's important behavior
obvious.

You are ready to use the Guides as design references rather than recipes. Start
with [Validation and types](../guides/validation-and-types.md) for trust
boundaries, [Concurrency and cycles](../guides/concurrency-and-cycles.md) for
execution policy, or [Choose a pattern](../patterns.md) to open a complete
application with the shape you need.
