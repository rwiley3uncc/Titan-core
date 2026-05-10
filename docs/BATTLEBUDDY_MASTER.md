# BattleBuddy Master

Last updated: 2026-05-09

Related docs:
- [BATTLEBUDDY_MIGRATION.md](C:/Users/mouse/DEV/Titan-core/docs/BATTLEBUDDY_MIGRATION.md)
- [CONNECTORS_SETUP.md](C:/Users/mouse/DEV/Titan-core/docs/CONNECTORS_SETUP.md)
- [AGENT_SYSTEM_OVERVIEW.md](C:/Users/mouse/DEV/Titan-core/docs/AGENT_SYSTEM_OVERVIEW.md)

## Purpose

BattleBuddy is the current user-facing assistant, UI gateway, and FastAPI runtime surface for the Titan platform.

## Continuity Reference Pattern

- `TITAN_STABILIZATION_CHECKPOINT.md` is the short-form continuity handoff for recent TitanEvent, ApprovalRequest, BattleBuddy emission, retention, approval visibility, and unified timeline work.
- `TITAN_MASTER_SYSTEM_SPEC.md` remains the authoritative architecture spec.
- Use the checkpoint first after context compaction.
- Use the master spec for subsystem ownership, runtime boundaries, and hard rules.

## Current Status

- Implemented
- Working
- Local-only
- Mid-migration naming state

## Runtime Ownership

- Primary runtime owner:
  - `Titan-core/titan_battlebuddy/main.py`
- Compatibility owner:
  - `Titan-core/titan_core/main.py`

## Architecture Summary

- FastAPI application runtime
- static UI served from `titan_ui/index.html`
- active route surface under `/api`
- Titan-AI handles reasoning/orchestration
- Titan Core package continues to host the active route implementations
- Titan Shared supplies the generic TitanEvent contract used for BattleBuddy runtime event output
- Titan Shared supplies the ApprovalRequest contract used for local approval visibility only

## Implemented Systems

- BattleBuddy FastAPI app
- health endpoint
- seed endpoint
- sitrep system
- chat system
- calendar source management
- constrained action execution
- plan approval/skip/replace routes
- memory route
- task route
- active rules system
- active executor system
- file-backed task store
- dismissed-items persistence
- summary-only TitanEvent emission to `Titan-core/data/events/titan_events.jsonl`
- event retention and archive safeguards for the TitanEvent log
- summary-only ApprovalRequest emission to `Titan-core/data/approvals/approval_requests.jsonl`

## Planned Systems

- clearer namespace cleanup after migration
- fuller shared UI extraction
- future stronger approval-centered agent surfaces
- future richer connector health/status

## Active Runtime Paths

- Folder:
  - `C:\Users\mouse\DEV\Titan-core`
- Primary runtime:
  - `python -m uvicorn titan_battlebuddy.main:app --reload`
- Compatibility runtime:
  - `python -m uvicorn titan_core.main:app --reload`
- Launchers:
  - `run_battlebuddy.ps1`
  - `start_battlebuddy.ps1`
  - `run_titan.ps1`
  - `start_titan.ps1`

## Active UI Paths

- `Titan-core/titan_ui/index.html`
- URL:
  - `http://127.0.0.1:8000/ui/index.html`

## APIs / Endpoints

- App-level:
  - `GET /`
  - `GET /health`
  - `POST /seed`
  - `GET /debug/verified-web`
- Chat:
  - `POST /api/chat`
  - `GET /api/memory`
  - `GET /api/tasks`
- Sitrep:
  - `GET /api/sitrep`
  - `GET /api/dismissed-items`
  - `POST /api/dismissed-items`
- Calendar sources:
  - `GET /api/calendar-sources`
  - `POST /api/calendar-sources`
  - `PATCH /api/calendar-sources/{source_id}`
  - `DELETE /api/calendar-sources/{source_id}`
- Execution / planning:
  - `POST /api/execute`
  - `POST /api/plan/approve-next`
  - `POST /api/plan/skip-next`
  - `POST /api/plan/replace-next`
  - `GET /api/action-log`
  - `GET /api/agent-memory`

## Sitrep System

- active route implementation:
  - `titan_core/api/sitrep.py`
- sources:
  - Canvas ICS
  - Outlook ICS
  - saved calendar source list
  - optional weather summary

## Chat System

- active route implementation:
  - `titan_core/api/chat.py`
- modes:
  - personal assistant
  - development assistant
- reasoning path:
  - Titan-AI through stable orchestration entrypoints
- event output:
  - emits summary-only `chat_request_received`, `chat_response_generated`, and `proposed_action_created` TitanEvent records
- approval visibility output:
  - may emit summary-only ApprovalRequest records for proposed constrained actions

## Executor / Rules Systems

- active rules:
  - `titan_core/rules.py`
- active executor:
  - `titan_core/executor.py`
- partial planning/agent-related endpoints:
  - `titan_core/api/execute.py`
- constrained execution event output:
  - emits summary-only `constrained_action_requested`, `constrained_action_allowed`, `constrained_action_blocked`, `constrained_action_executed`, `constrained_action_failed`, and `constrained_action_client_reported`
- approval visibility output:
  - may emit summary-only blocked ApprovalRequest records for blocked constrained actions

## Memory / Task Systems

- active direct memory flow:
  - `titan_core/api/chat.py`
  - `titan_core/memory.py`
- active file-backed tasks:
  - `titan_core/task_store.py`
- draft persistence:
  - Placeholder / partial legacy history only
- full chat/session persistence:
  - Placeholder / partial legacy history only

## Connector Systems

- Canvas ICS
- Outlook ICS
- multi-calendar source storage in `data/calendar_sources.json`
- env-driven connector configuration
- sitrep event output:
  - emits summary-only `sitrep_refresh_requested`, `sitrep_refresh_succeeded`, `sitrep_refresh_failed`, and `calendar_source_degraded`

## Runtime Event Output

- event contract owner:
  - `Titan-shared/titan_shared/contracts/titan_event.py`
- active event helper:
  - `titan_core/event_log.py`
- active event log path:
  - `Titan-core/data/events/titan_events.jsonl`
- retention defaults:
  - `1000` recent events
  - `2 MB` log-size limit
- archive path:
  - `Titan-core/data/events/archive/`
- event records are summary-only and must not include secrets, full user messages, or full calendar contents

## Runtime Approval Output

- approval contract owner:
  - `Titan-shared/titan_shared/contracts/approval_request.py`
- active approval helper:
  - `titan_core/approval_log.py`
- active approval log path:
  - `Titan-core/data/approvals/approval_requests.jsonl`
- approval records are structure/visibility only right now
- duplicate suppression is lightweight and file-local
- approval records are summary-only and must not include secrets, full user messages, or full calendar/task contents
- current status vocabulary:
  - `pending`
  - `approved`
  - `rejected`
  - `expired`
  - `cancelled`
  - `blocked`
  - `completed`
  - `failed`
- current risk vocabulary:
  - `low`
  - `medium`
  - `high`
  - `critical`
  - `unknown`

## Safety Boundaries

- local-only runtime
- no unrestricted autonomy
- constrained executor behavior
- no execution of uploaded dev files
- no destructive automation without explicit approval
- no new approvals, execution controls, or autonomy were added by the TitanEvent emission path
- ApprovalRequest emission does not add approval execution, auto-approval, or new executable capability

## Active vs Legacy

- Active:
  - `titan_battlebuddy/main.py`
  - `titan_core/api/*`
  - `titan_core/rules.py`
  - `titan_core/executor.py`
  - `titan_ui/index.html`
- Transitional:
  - `titan_core/main.py`
- Legacy / archive:
  - `docs/archive/legacy_backend/titan_api/*`
  - `docs/archive/legacy_tools/tools/*`
  - `docs/archive/legacy_ui/app.js`

## Legacy Ambiguity Warnings

- do not mistake archived `titan_api` for the active backend
- do not patch archived `tools` instead of active `titan_core` systems
- do not assume archived `app.js` controls the current UI

## Validation

- `python run_battlebuddy_migration_tests.py`
- `python run_environment_validation.py`
- active runtime import can be checked through `titan_battlebuddy.main`

## Known Limitations

- migration-era split between `titan_battlebuddy` and `titan_core`
- some legacy persistence features are richer than the active path
- UI logic remains largely inline in `titan_ui/index.html`
- Titan Sentry and Titan Forge are not yet rewritten to emit generic TitanEvent directly
- full lifecycle-aware approval queue management remains deferred

## Future Direction

- gradual namespace cleanup
- deliberate migration of useful legacy persistence/approval features
- shared UI convergence with Titan Command

## Hard Rules

- BattleBuddy remains in `Titan-core` until a safe migration plan exists
- active runtime path is `titan_battlebuddy.main:app`
- legacy paths require explicit revival before editing
