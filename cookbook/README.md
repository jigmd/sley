# Caskada Cookbook

The cookbook teaches Caskada through small projects that fit in a reader's head.
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
7. [`python-supervisor`](./python-supervisor): named nested-Flow exits and
   supervision.

The two TypeScript examples cover the same authoring model:

- [`typescript-chat`](./typescript-chat): a typed self-loop and hard terminal.
- [`typescript-agent`](./typescript-agent): typed state and a named decision
  loop.

## Find an Example

- [Python catalog](../docs/cookbook/python.md)
- [TypeScript catalog](../docs/cookbook/typescript.md)
- [Complexity rubric](../docs/cookbook/points.md)

Complexity metadata estimates how much a reader must keep in mind. It is not a
production-readiness score.

## Learning Contract

Examples prefer readable, recognizable code over generalized helpers or
production scaffolding. External services are replaced by test-owned fakes in
verification, while teaching source executes the real Caskada graph.

Comments scale with the learning path: introductory examples explain basic
Caskada mechanics, and advanced examples explain only the new mechanism they
introduce. Types are used when they clarify a lesson and are kept in one file so
readers can skip them.
