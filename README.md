# Titan BattleBuddy

Titan BattleBuddy is the user-facing controller and application gateway for the
Titan platform.

It continues to own:

- the FastAPI app and routes
- UI delivery
- sitrep and verified-source flows
- memory, task, and settings integration
- action planning and execution endpoints

Titan-AI now owns the AI orchestration path, including prompt assembly, local
model routing, and reply generation. Titan BattleBuddy collects application context
and calls Titan-AI through a stable interface.

Migration note:

- `titan_battlebuddy` is the new public namespace
- `titan_core` remains available temporarily for compatibility
- old startup commands and URLs are still supported during the staged rename

## Startup Commands

New:

```text
python -m uvicorn titan_battlebuddy.main:app --reload
```

Compatibility path:

```text
python -m uvicorn titan_core.main:app --reload
```

Validation commands:

```text
python run_battlebuddy_migration_tests.py
python run_environment_validation.py
```

## Local-Only Design

Titan BattleBuddy remains a local controller and UI gateway. It keeps runtime,
routes, sitrep handling, settings, and action-control behavior local while
delegating AI reply orchestration to Titan-AI.
