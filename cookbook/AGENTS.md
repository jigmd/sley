# Cookbook

## Purpose

- Teach Caskada patterns through code that fits in a reader's head.
- Optimize for readability, ease of understanding, and progressive learning.

## Ownership

- Owns all cookbook projects, their source files, READMEs, sample data, and
  instructional metadata.
- Production hardening belongs outside the cookbook unless it is the pattern an
  example explicitly teaches.

## Local Contracts

- Each example must have one primary lesson and the smallest code needed to show
  it honestly.
- Prefer obvious linear code over reusable abstractions, exhaustive validation,
  defensive wrappers, or generalized helpers.
- Do not add production-oriented retries, cancellation plumbing, schema
  validation, deterministic reconstruction, or error taxonomies unless that is
  the named subject of the example.
- Keep the Caskada behavior being taught visible in the code. Supporting prose
  should clarify the example, not carry its central logic.
- Keep dedicated map/reduce helpers or explicit Map and Reduce nodes only when
  that pattern is the lesson. Otherwise prefer a local Flow combiner when it
  removes concepts from the example.
- Strong typing should clarify the lesson. Use a concise annotation or local cast
  when exhaustive runtime validation would dominate the example.
- Keep project type definitions in one dedicated file so readers can skip them
  without losing the workflow. If typing does not clarify that example, omit it.
- Maintain a deliberate mix of typed and untyped cookbook projects; typing is a
  teaching choice, not mandatory ceremony in every example.

## Work Guidance

- Read the existing example and its README before editing; preserve recognizable
  names and control flow unless changing them is part of the lesson.
- Treat substantial line-count or concept growth as a design smell requiring
  explicit justification.
- Scale comments with the learning path. Introductory examples explain basic
  Caskada mechanics at the point of use; advanced examples assume earlier
  concepts and comment only the new mechanism they introduce.
- Put caveats in a short README note. Do not turn the main example into a catalog
  of edge cases.

## Verification

- Parse changed source and type-check examples that present themselves as typed.
- Run formatting and `git diff --check`.
- Review the final example in isolation for teaching clarity and lesson focus;
  passing production-oriented checks is not a substitute for this review.

## Child DOX Index

- No child AGENTS.md files are currently required; each project follows this
  cookbook-wide teaching contract.
