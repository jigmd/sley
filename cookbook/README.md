# Sley Cookbook

The cookbook teaches Sley through small projects that fit in a reader's head.
Each project has one primary lesson and its own README.

## Suggested Learning Path

1. [`python-hello-world`](./python-hello-world): `@node`, shared state, and a
   normal leaf.
2. [`python-flow`](./python-flow): unlabelled links and deliberate `end()`.
3. [`python-batch-node`](./python-batch-node): fan-out, worker outputs, and a Flow
   combiner.
4. [`python-nested-batch`](./python-nested-batch): nested scope boundaries and
   two combine levels.
5. [`python-agent`](./python-agent): named routes and a search loop.
6. [`python-rag`](./python-rag): offline and online workflows with explicit state
   handoff.
7. [`python-supervisor`](./python-supervisor): structured independent feedback
   and bounded revision.
8. [`python-orchestrator-workers`](./python-orchestrator-workers): dynamic
   planning, worker fan-out, and an integration editor.
9. [`python-best-of-n-judge`](./python-best-of-n-judge): blind pairwise selection
   among qualitatively different candidates.
10. [`python-quality-loop`](./python-quality-loop): a reference-grounded capstone
    with component and whole-artifact quality gates.

The TypeScript path covers the authoring model from one node through bounded
quality orchestration:

1. [`typescript-hello-world`](./typescript-hello-world): one typed node and an
   ordinary leaf.
2. [`typescript-workflow`](./typescript-workflow): a small linear topology.
3. [`typescript-inspection`](./typescript-inspection): compiled descriptions and
   explicit run results.
4. [`typescript-retry-recovery`](./typescript-retry-recovery): node retry and
   local recovery.
5. [`typescript-batch`](./typescript-batch): concurrent fan-out and combine.
6. [`typescript-nested-flow`](./typescript-nested-flow): a concurrent multi-step
   worker scope.
7. [`typescript-resilient-batch`](./typescript-resilient-batch): Flow recovery
   with settled branch terminals.
8. [`typescript-chat`](./typescript-chat): a typed self-loop and hard terminal.
9. [`typescript-agent`](./typescript-agent): typed state and a named decision
   loop.
10. [`typescript-mcp`](./typescript-mcp): MCP discovery, validation, and
    execution over stdio.
11. [`typescript-orchestrator-workers`](./typescript-orchestrator-workers):
    dynamic planning, worker fan-out, and integration.
12. [`typescript-quality-loop`](./typescript-quality-loop): bounded component
    and whole-artifact evaluation loops.

## Find an Example

- [Choose an example](../docs/examples/README.md)
- [Python catalog](../docs/examples/python.md)
- [TypeScript catalog](../docs/examples/typescript.md)

Complexity metadata estimates how much a reader must keep in mind. It is not a
production-readiness score.

## Learning Contract

Examples prefer readable, recognizable code over generalized helpers or
production scaffolding. External services are replaced by test-owned fakes in
verification, while teaching source executes the real Sley graph.

Comments scale with the learning path: introductory examples explain basic
Sley mechanics, and advanced examples explain only the new mechanism they
introduce. Types are used when they clarify a lesson and are kept in one file so
readers can skip them.
