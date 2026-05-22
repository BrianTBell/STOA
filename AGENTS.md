# Agent Operating Instructions

This file is the source of truth for how AI coding agents (Claude Code) should work in this repository.

## Read first

Before doing anything, read these in order:

1. `PROJECT.md` — what we're building and why
2. `ARCHITECTURE.md` — stack and pipeline
3. `SCHEMA.md` — data model
4. `ROADMAP.md` — phased plan and current scope

If any of these conflict, `PROJECT.md` wins on intent and `ARCHITECTURE.md` wins on technical decisions.

## Working principles

**Phased delivery.** Work the roadmap in order. Do not start Phase N+1 until Phase N produces verified, working output. The owner will confirm phase completion before you advance.

**Vertical slices over horizontal scaffolding.** Resist the urge to scaffold the entire repo upfront. Build one working end-to-end thing at a time, even if it's tiny. A working ingestion script with hardcoded values is more valuable than empty folders for every future component.

**Validate prompts before building infrastructure.** The most expensive mistake in this project is wiring up Neo4j, FastAPI, and a frontend around a Claude prompt that produces garbage. Before adding any infrastructure, the upstream AI step must produce output the owner has reviewed and trusts.

**Ask before adding dependencies.** New libraries, new services, new files at the root level — pause and confirm. Small dependencies in existing components are fine.

**Document decisions inline.** When you make a meaningful architectural choice (a new library, a schema shape, a prompt structure), update the relevant `.md` file in the same session. Stale docs are worse than missing docs.

## Owner context

The owner is a mechanical engineer with strong Python fundamentals but no prior experience with FastAPI, Neo4j, React, or LLM API work. Optimize for:

- Clear explanations of what's happening and why
- Minimal magic — prefer explicit, readable code over clever abstractions
- Comments where a non-expert would otherwise be stuck
- Output the owner can actually verify (printed JSON, simple test scripts, README updates)

The owner steers conceptually. You do the implementation. The owner will ask questions and request changes — treat those as the most important signal in the loop.

## What not to do

- Do not build the frontend before the backend produces queryable data
- Do not add authentication, user accounts, or community features in Phase 1–5
- Do not pull in fine-tuning, embeddings training, or any custom model work — use off-the-shelf
- Do not gate-keep content programmatically — confidence scoring is signal, not a filter
- Do not handle video, audio, or non-text sources yet — arXiv text only for now (see `ROADMAP.md`)

## Style

- Python 3.11+
- Type hints on function signatures
- `ruff` for linting, `black` for formatting (add when first needed)
- Conventional commit messages (`feat:`, `fix:`, `docs:`, `chore:`)
- One concern per file, small modules over large ones

## Session protocol

At the start of each session:
1. Read this file and the four docs above
2. Identify the current phase from `ROADMAP.md`
3. Confirm with the owner what they want to work on
4. Work in small, verifiable steps

At the end of each session:
1. Update any docs that changed
2. Summarize what was built and what's next
3. Flag any open questions for the owner
