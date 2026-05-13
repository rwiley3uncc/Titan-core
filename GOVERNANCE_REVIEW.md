<!-- Copyright (c) 2026 Ron Wiley. All rights reserved. -->

# Governance Review

## Repository classification

- Repository: Titan-core / Titan BattleBuddy
- Recommended classification: private or source-available candidate
- Public-ready status: not public-ready

## Current license state

- Existing `LICENSE` file detected and preserved
- Current license posture should be reviewed for consistency with the wider Titan platform
- Do not overwrite the existing license without a deliberate platform-level license decision

## Recommended license posture

- Keep private or source-available until a deliberate release decision is made
- Treat this repository as platform-internal runtime and execution-boundary code rather than a public standards layer

## Governance items added in this pass

- `SECURITY.md`
- `CONTRIBUTING.md`
- `THIRD_PARTY.md`
- `RELEASE_CHECKLIST.md`

## Exposure risks

- runtime logs currently tracked in Git:
  - `battlebuddy_8001.err.log`
  - `battlebuddy_8001.log`
  - `battlebuddy_8001_refine.err.log`
  - `battlebuddy_8001_refine.log`
  - `battlebuddy_uvicorn.err.log`
  - `battlebuddy_uvicorn.log`
- mutable local data currently tracked in Git:
  - `data/calendar_sources.json`
  - `data/dismissed_items.json`
  - `data/tasks.json`
- local-only files present on disk:
  - `.env`
  - `.venv/`
  - `.local_artifacts/`
  - `titan.db`
  - `data/events/*.jsonl`
  - `data/approvals/`
- documentation still contains local absolute paths and BattleBuddy-specific assistant framing that should remain scoped carefully

## Recommended cleanup actions not performed automatically

- consider `git rm --cached` for tracked runtime logs
- review whether tracked mutable local data should move to fixtures, examples, or local-only defaults
- replace public-facing absolute local file links with repo-relative links where practical
- continue staged rename planning from `Titan-core` to `Titan BattleBuddy` without breaking runtime behavior

## Third-party and provenance concerns

- `docs/archive/` should not receive blanket copyright headers
- archived code paths require provenance review before any public release
- dependency attribution work is still incomplete

## Manual legal and IP review items

- confirm repo-level license consistency against the rest of Titan
- confirm whether archived legacy materials can remain in any public release
- review whether the BattleBuddy rename plan creates trademark or packaging implications
