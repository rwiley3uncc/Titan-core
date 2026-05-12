# BattleBuddy Agent Notes

Last updated: 2026-05-10

This file is intentionally scoped to BattleBuddy-only notes so it does not duplicate the broader agent architecture docs.

Canonical ecosystem agent design:

- [Titan-Command/docs/AGENT_SYSTEM_OVERVIEW.md](C:/Users/mouse/DEV/Titan-Command/docs/AGENT_SYSTEM_OVERVIEW.md)
- [Titan-Command/docs/AGENT_FRAMEWORK_PLAN.md](C:/Users/mouse/DEV/Titan-Command/docs/AGENT_FRAMEWORK_PLAN.md)

## Current BattleBuddy Reality

BattleBuddy currently has partial action-proposal behavior, not a full platform agent stack.

- chat may return reviewable proposed actions
- executable actions remain allow-listed and approval-gated
- plan/reviewer/executor/auditor layering is not implemented here as a full subsystem

## Local Files Still Relevant

- `titan_core/agent.py`
- `titan_core/agent_memory.py`
- `titan_core/agent_smoke.py`

Use this file only for BattleBuddy-local notes. Use Titan Command docs for platform-level agent behavior, safety boundaries, and future architecture.
