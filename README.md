<!-- Copyright (c) 2026 Ron Wiley. All rights reserved. -->

# Titan BattleBuddy / Titan Core

This repo currently hosts the active BattleBuddy runtime plus the transitional `titan_core` compatibility namespace.

Current synchronized runtime:

- `Role`: BattleBuddy interaction shell
- `Port`: `8001`
- `UI`: `http://127.0.0.1:8001/ui/index.html`

Canonical local runtime map:

- `Titan Command`: `http://127.0.0.1:8000/`
- `BattleBuddy`: `http://127.0.0.1:8001/ui/index.html`
- `Titan Sentry`: `http://127.0.0.1:8002/ui/index.html`
- `Titan Forge`: `http://127.0.0.1:8003/ui/index.html`

Recommended operator startup:

1. Start Titan Command on `8000`.
2. Use Titan Command to launch BattleBuddy when you need the runtime.

Direct local runtime startup, if needed for debugging or isolated validation:

```powershell
cd <repo-root>
python -m uvicorn titan_battlebuddy.main:app --host 127.0.0.1 --port 8001
```

Compatibility startup, for namespace-transition debugging only:

```powershell
python -m uvicorn titan_core.main:app --host 127.0.0.1 --port 8001
```

Expected readiness check:

- `GET http://127.0.0.1:8001/health` returns success before relying on BattleBuddy UI or sitrep routes.

Validation:

```powershell
python run_battlebuddy_migration_tests.py
python run_environment_validation.py
python run_student_mode_validation.py
```

Launcher/preflight notes:

- `Titan-Command\scripts\launch_battlebuddy_runtime.ps1` now records the resolved Python path and any optional WSL helper status in launcher metadata.
- The BattleBuddy backend can still start even if the optional WSL `searx.webapp` helper is unavailable or explicitly disabled.
- The current local launcher still has optional WSL coupling for the helper path; that remains a portability gap rather than a hidden requirement.

Student mode notes:

- A minimum local-first `student_ops` mode is now documented for Monday-use planning.
- BattleBuddy already exposes sitrep, class/deadline visibility, study-block suggestions, and verified-source fail-closed behavior that this mode builds on.
- Course-material organization is read-only and manifest-based under `data/courses/`.
- A first-scope local retrieval MVP now supports manifest-listed `.md`, `.txt`, and `.json` course files for `student_ops`.
- Current retrieval remains local-only, read-only, and fail-closed.

First-scope container build:

```powershell
# run from the Titan workspace root
docker buildx build --load --build-context titan_shared=.\Titan-shared --build-context titan_ai=.\Titan-AI -f .\Titan-core\Dockerfile .\Titan-core
```

First-scope startup gate:

```powershell
python run_environment_validation.py --startup-gate
```

First-scope Docker scope notes:

- the image is limited to BattleBuddy only
- `Titan-shared` and `Titan-AI` are installed as package dependencies
- local runtime data, approval/event JSONL, launcher logs, `.local_artifacts`, and `titan.db` are not baked into the image
- the Dockerfile now includes a lightweight healthcheck against `/health`
- no Compose file is included in this batch
- no Titan Command or Titan Forge containerization is included in this batch

BattleBuddy chat architecture:

- `titan_core/api/chat.py` is the active FastAPI route and top-level orchestration layer for chat.
- Helper logic that used to accumulate inside `chat.py` is now split across focused modules:
  - `titan_core/chat_mode.py`: mode normalization, assistant-mode checks, route classification, personal intent detection
  - `titan_core/chat_memory.py`: memory save detection, scoring, extraction, duplicate/match lookup, memory answer formatting
  - `titan_core/chat_tasks.py`: deterministic task command parsing, due/time helpers, task response builders
  - `titan_core/chat_actions.py`: proposed-action shaping, plan/action conversion, replace/skip/approve-next helpers, approval/action metadata preparation
  - `titan_core/chat_responses.py`: response finalization, metadata attachment, verified-web formatting, upload sanitization, grounded/personal response builders
- Future chat-related helpers should be added to the appropriate helper module instead of growing `titan_core/api/chat.py` back into a monolith.

Important note:

- Some historical launcher scripts and older docs still reference legacy BattleBuddy `8000` behavior. The canonical runtime map above and the synchronized Titan ecosystem documentation treat `8001` as the active side-by-side BattleBuddy runtime port.

Documentation:

- [Titan Platform Identity](../Titan-shared/docs/TITAN_PLATFORM_IDENTITY.md)
- [BattleBuddy](../Titan-AI/docs/BATTLEBUDDY.md)
- [Architecture](../Titan-shared/docs/TITAN_TECHNICAL_ARCHITECTURE.md)
- [API Reference](../Titan-AI/docs/API_REFERENCE.md)
- [Runtime Contract](../Titan-shared/docs/runtime_contracts/BATTLEBUDDY_RUNTIME_CONTRACT.md)
- [Student Mode](../Titan-shared/docs/TITAN_STUDENT_MODE.md)
- [Local Course Retrieval MVP](../Titan-shared/docs/TITAN_LOCAL_COURSE_RETRIEVAL_MVP.md)
