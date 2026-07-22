# CLAUDE.md — Project Akiha

This file is read by the AI assistant at the start of every session working on this repo. Its job is to keep architectural discipline consistent across many separate sessions, months apart, possibly with context that doesn't carry over. Follow it even when a shortcut looks easier — the shortcuts are exactly what this file exists to prevent.

## What this project is

A Windows desktop app combining an AI desktop pet, an AI companion chat, and a local AI assistant into one modular product. Long-term project (months/years), built in phases. Full architecture rationale lives in `ARCHITECTURE.md` — read that before touching structure-level decisions. This file is the day-to-day ruleset.

## The Five Non-Negotiables

These are expensive to fix later if violated early. Never break them to "move faster."

1. **`core/` never imports PySide6, Ollama's client, or any OS-specific library.** Core logic depends only on interfaces defined in `core/interfaces/`. If you're writing code in `core/` and reaching for a Qt or Ollama import, stop — that logic belongs in `ui/` or `ai/adapters/`, or the interface is missing a method.
2. **All AI calls go through the `AIProvider` interface**, never a direct Ollama client call outside `ai/providers/`.
3. **Every schema change is a new migration file** in `database/migrations/`, never a hand-edit of an existing table definition once it's shipped.
4. **Cross-module communication goes through the EventBus.** If module A needs to react to something in module B, that's a new event type, not a direct import/reference between A and B.
5. **Every automation/assistant action is a `Command` object that passes through `PermissionGate`** before executing — even during prototyping. Don't add a "temporary" direct `os.system()` call with intent to fix it later; it won't get fixed later.

## Current phase

*(Update this section as the project progresses — it's the most important line in this file for keeping the AI's suggestions scoped correctly.)*

- Current milestone: **Phase 1 — Desktop Pet** (feature complete; no AI integration yet)
- Do not build ahead of the current phase unless explicitly asked. If asked to add a feature from a later phase, flag that it's out of current sequence before proceeding.

## Coding conventions

- Python 3.12+, type hints on all public functions/methods.
- `black` formatting, `ruff` for linting — run before considering a change done.
- Dataclasses (or pydantic models where validation matters) for data structures, not raw dicts passed between modules.
- Async by default for anything touching I/O (AI calls, file access, DB) — no blocking calls on the Qt UI thread.
- Docstrings on every public class and function — one line minimum, explaining *why* it exists if the name doesn't make it obvious.
- Tests live next to what they test in `tests/unit/` or `tests/integration/`, mirroring the source tree.

## Security rules (always apply, regardless of phase)

- Never let AI-generated output directly trigger system commands. AI output can only propose a `Command` object; execution always goes through `PermissionGate`.
- Never hardcode secrets, API keys, or tokens. Config values only, sourced from user config or environment variables, never committed.
- Treat plugin code as untrusted, always — no exceptions for "it's just my own test plugin."
- No `os.system()` / `subprocess` calls with unsanitized string interpolation, ever — build argument lists, not shell strings.
- Full detail: see `SECURITY.md`.

## Before making a structural change

If a change would touch folder structure, add a new cross-cutting service, or change how modules communicate — check `ARCHITECTURE.md` first and flag if the change conflicts with a documented decision, rather than silently deviating from it.

## What NOT to do

- Don't add a dependency without checking it's actively maintained and doesn't pull in a large unnecessary tree — this app needs to stay lightweight and fast-starting.
- Don't skip writing a migration "just this once."
- Don't build Live2D, voice, or plugin-loading features unless the current phase (above) has reached them.
- Don't suppress or work around a failing test instead of fixing the underlying issue.
- Don't add UI polish before the underlying feature's logic has test coverage.

## When context is unclear

If a past session's intent isn't obvious from code/comments/git history, ask rather than guessing — a wrong architectural assumption compounds across a multi-year project far more than a wrong UI detail does.
