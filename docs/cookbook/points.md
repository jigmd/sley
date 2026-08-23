# Cookbook Complexity

Complexity scores help readers choose an example. They estimate how much a
reader must keep in mind; they do not measure code quality, completeness, or
production readiness.

## Scoring

### Sley Concepts

- 0.5 per distinct function-backed node in the primary graph.
- 1 for named branching or a self-loop; 2 when both are central.
- 2 for meaningful nested Flow boundaries.
- 2 for repeated-emission fan-out.
- 2 for a custom Flow combine callback.
- 1 for local concurrency greater than one.
- 1 for retry or recovery when it is part of the lesson.
- 1 for compiled graph inspection when central.

### Application Logic

- 1 for nontrivial parsing or transformation.
- 1 for a meaningful persistence layer or complex file I/O.
- 1 per distinct external service category, up to 3.
- 1 for a substantial interactive UI or protocol adapter.
- 1 for advanced resilience or synchronization that the example intentionally
  teaches.

### Readability Adjustment

Add 1 when several independent concepts must be understood together even if the
source is short. Subtract 1 when the application domain makes a framework
concept unusually obvious. Keep the final score at or above 1.

File count, comments, type annotations, and production hardening do not increase
complexity by themselves. A simpler rewrite should normally retain or reduce the
score.

## Tiers

| Complexity | Tier         | Reader expectation                                           |
| ---------: | ------------ | ------------------------------------------------------------ |
|        1-4 | Introductory | One core mechanism with little surrounding code              |
|      4.5-8 | Intermediate | Several connected mechanisms or one application integration  |
|     8.5-16 | Advanced     | Nested control, aggregation, protocols, or multiple services |
|      16.5+ | Reference    | Several advanced concerns combined in one project            |

Scores are maintained in each project README front matter. When a project's
primary lesson or cognitive load changes materially, update its score and this
catalog together.
