# Agent Skills

## Purpose

- Give coding agents portable, on-demand knowledge for building with Sley.

## Ownership

- Owns cross-client Agent Skills under `<name>/`.
- Public docs and runtime contracts remain the source of truth for Sley behavior.

## Local Contracts

- Each skill follows the Agent Skills specification and lives at
  `<name>/SKILL.md`.
- Keep descriptions precise enough to trigger only for the capability they name.
- Keep shared decisions in `SKILL.md`; put language-specific or advanced detail
  behind explicit reference pointers.
- `sley/references/` is generated from selected canonical docs by
  `.github/scripts/generate-sley-skill.js`. Edit the source docs, then
  regenerate the copies.

## Work Guidance

- Write positive, checkable instructions with an explicit completion criterion.
- Remove generic coding advice, duplicated rules, and speculative branches.

## Verification

- Run `node .github/scripts/generate-sley-skill.js`; a second run must leave no
  diff.
- Run `uvx --from skills-ref agentskills validate skills/<name>` for each
  changed skill.

## Child DOX Index

- No child AGENTS.md files are currently required.
