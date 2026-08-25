---
description: Turn tangled workflow control flow into a small, explicit graph of ordinary Python or TypeScript functions.
---

# Sley

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/jigmd/sley/main/media/sley-wordmark-reverse.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/jigmd/sley/main/media/sley-wordmark.svg">
    <img width="320" alt="Sley" src="https://raw.githubusercontent.com/jigmd/sley/main/media/sley-wordmark.svg">
  </picture>
</p>

## Complex workflows. Obvious code.

Sley turns tangled workflow logic into code your team can scan and change with
confidence. A workflow rarely starts tangled. It gets there one condition,
callback, counter, and fallback at a time, until the work still makes sense but
its shape no longer does.

Sley puts that shape back in front of you. Write ordinary functions, connect
the paths they may take, and run the graph. Branching, fan-out, joins, retries,
and nested workflows stay visible, the final state comes back directly, and
your application remains ordinary Python or TypeScript.

## Small by design

- A **node** is one ordinary synchronous or asynchronous function.
- A **link** makes one allowed next step visible.
- `emit()` chooses one or more paths.
- A **Flow** waits for those paths and `run()` returns their final shared state.

That small model is the point. Sley owns in-process graph execution. Your code
keeps validation, storage, services, UI, and every domain decision.

Use Sley when branching and synchronization have made a workflow's shape hard
to see. Keep ordinary calls, conditions, loops, `asyncio.gather`, or
`Promise.all` while they still explain the workflow clearly.

## Learn to think in graphs

These docs do more than teach method names. You will begin with no graph-runtime
vocabulary and finish able to:

- choose node boundaries that keep work readable;
- model decisions, loops, fan-out, and fan-in without hiding control;
- decide what belongs in shared state, branch input, and terminal output;
- place scope, concurrency, retry, and recovery boundaries deliberately;
- recognise graph designs that are doing too much;
- test and explain a workflow from its observable behavior.

The judgment transfers beyond Sley. The examples simply give you a small,
runnable place to build it.

## Start with one file

```bash
pip install sley
```

```bash
npm install @jigging/sley
```

The [Quickstart](quickstart.md) takes one file from installation to a completed
run with visible output. No service, account, API key, or application framework
is required.
