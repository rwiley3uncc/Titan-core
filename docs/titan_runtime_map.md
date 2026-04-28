# Titan Runtime Map

## Active Runtime Files
These files are on the actual runtime path when Titan is started from `titan_core/main.py`.

### App entry and mounted routes
- `titan_core/main.py`
  - Creates the FastAPI app
  - Creates database tables with `Base.metadata.create_all(bind=engine)`
  - Mounts `/ui`
  - Includes `/api/chat`, `/api/execute`, and `/api/sitrep` routers
- `titan_core/api/chat.py`
  - Handles `POST /api/chat`
  - Routes between memory save/recall, grounded personal-assistant intents, rule-based action proposals, and development-assistant LLM replies
  - Also exposes `GET /api/memory`
- `titan_core/api/execute.py`
  - Handles `POST /api/execute`
  - Passes action dictionaries to the active executor
- `titan_core/api/sitrep.py`
  - Handles `GET /api/sitrep`
  - Builds the dashboard sitrep payload and spoken briefing

### Active frontend
- `titan_ui/index.html`
  - Active browser UI entrypoint served from `/ui/index.html`
  - Contains the actual live dashboard markup and the main inline JavaScript controller
  - Calls:
    - `GET /api/sitrep`
    - `POST /api/chat`
    - `POST /api/execute`

### Active supporting runtime modules
- `titan_core/config.py`
  - Loads environment-driven settings
- `titan_core/db.py`
  - Database engine, session factory, dependency provider, and `Base`
- `titan_core/models.py`
  - SQLAlchemy models used by the active app
- `titan_core/schemas.py`
  - Pydantic request/response and brain schemas
- `titan_core/brain.py`
  - Development-assistant reply orchestration
- `titan_core/rules.py`
  - Rule-based action proposal and fallback reply generation
- `titan_core/policy.py`
  - Filters proposed actions and applies safety rules
- `titan_core/validator.py`
  - Cleans and clamps brain output
- `titan_core/memory.py`
  - Recent-memory retrieval used by the brain
- `titan_core/tools.py`
  - Local time/date helpers for rule responses
- `titan_core/executor.py`
  - Active action executor for `/api/execute`
- `titan_core/canvas_feed.py`
  - Imports Canvas ICS data
- `titan_core/outlook_feed.py`
  - Imports Outlook ICS data
- `titan_core/planning.py`
  - Defines `PlannerItem`, `StudyBlockSuggestion`, and `Sitrep` dataclasses
- `titan_core/sitrep.py`
  - Computes today items, must-do items, open items, and suggested study blocks
- `titan_core/weather.py`
  - Fetches weather summary for sitrep
- `titan_brain/local_llm.py`
  - Sends development-assistant prompts to the local Ollama backend

### Active runtime tree
Starting from `titan_core/main.py`, the active dependency tree looks like this:

- `titan_core/main.py`
  - `titan_core/api/chat.py`
    - `titan_core/brain.py`
      - `titan_core/schemas.py`
      - `titan_core/rules.py`
        - `titan_core/tools.py`
      - `titan_core/policy.py`
        - `titan_core/schemas.py`
      - `titan_core/validator.py`
        - `titan_core/schemas.py`
      - `titan_core/memory.py`
        - `titan_core/models.py`
          - `titan_core/db.py`
      - `titan_brain/local_llm.py`
    - `titan_core/api/sitrep.py`
      - `titan_core/canvas_feed.py`
        - `titan_core/planning.py`
      - `titan_core/outlook_feed.py`
        - `titan_core/planning.py`
      - `titan_core/config.py`
      - `titan_core/planning.py`
      - `titan_core/sitrep.py`
        - `titan_core/planning.py`
      - `titan_core/weather.py`
    - `titan_core/config.py`
    - `titan_core/db.py`
    - `titan_core/models.py`
    - `titan_core/rules.py`
    - `titan_core/schemas.py`
  - `titan_core/api/execute.py`
    - `titan_core/executor.py`
  - `titan_core/api/sitrep.py`
  - `titan_core/config.py`
  - `titan_core/db.py`
  - `titan_core/models.py`
  - mounted static UI: `titan_ui/index.html`

## Indirect Runtime Files
These are used because active modules import them, even though they are not entrypoints or top-level routes.

### Imported by `titan_core/api/chat.py`
- `titan_core/brain.py`
- `titan_core/api/sitrep.py`
- `titan_core/config.py`
- `titan_core/db.py`
- `titan_core/models.py`
- `titan_core/rules.py`
- `titan_core/schemas.py`

### Imported by `titan_core/brain.py`
- `titan_core/schemas.py`
- `titan_core/rules.py`
- `titan_core/policy.py`
- `titan_core/validator.py`
- `titan_core/memory.py`
- `titan_brain/local_llm.py`

### Imported by `titan_core/api/sitrep.py`
- `titan_core/canvas_feed.py`
- `titan_core/outlook_feed.py`
- `titan_core/config.py`
- `titan_core/planning.py`
- `titan_core/sitrep.py`
- `titan_core/weather.py`

### Imported by `titan_core/models.py`
- `titan_core/db.py`

### Imported by `titan_core/rules.py`
- `titan_core/tools.py`

## Legacy / Unused Files
These files exist in the repo but are not on the runtime path started by `titan_core/main.py`.

### Legacy parallel backend
- `titan_api/main.py`
  - Older full FastAPI app with auth, conversations, audit logs, and approval flows
  - Not imported or mounted by `titan_core/main.py`
- `titan_api/auth.py`
  - JWT auth for the legacy backend
  - Only used by `titan_api/main.py`
- `titan_api/dispatcher.py`
  - Legacy executor that persists tasks, memories, and drafts
  - Not used by the active `/api/execute`
- `titan_api/schemas.py`
  - Legacy chat request/response schemas
  - Not used by the active `titan_core` routes
- `titan_api/__init__.py`
  - Package marker only

### Older or alternate frontend/controller files
- `titan_ui/app.js`
  - Older lightweight chat controller
  - Not referenced by `titan_ui/index.html`
  - No `<script src="app.js">` is present in the active page
- `tools/controller.py`
  - Standalone controller for rules + executor
  - Not imported by the active app
- `tools/rules.py`
  - Separate older rule system with app-launch logic
  - Not used by `titan_core`
- `tools/executor.py`
  - Separate older executor
  - Not used by `titan_core`
- `tools/apps.py`
  - Standalone helper for app/folder opening
  - Not referenced by active code

### Active package files that appear currently unused by `titan_core/main.py`
- `titan_core/json_utils.py`
  - Present but not imported on the active path
- `titan_core/executor.py` supports `open_url`, but no active proposer currently emits that action type

### Likely dormant package markers
- `titan_core/__init__.py`
- `titan_brain/__init__.py`

## Duplicate Systems
The repo contains overlapping systems in both `titan_core` and `titan_api`.

### FastAPI app entrypoints
- Active:
  - `titan_core/main.py`
- Legacy duplicate:
  - `titan_api/main.py`

### Chat endpoint stacks
- Active:
  - `titan_core/api/chat.py`
- Legacy duplicate:
  - `titan_api/main.py` has its own `/chat` endpoint, memory flow, and brain integration

### Memory save/recall logic
- Active:
  - `titan_core/api/chat.py`
  - `titan_core/memory.py`
- Legacy duplicate:
  - `titan_api/main.py`
  - `titan_api/dispatcher.py`

### Action execution systems
- Active:
  - `titan_core/api/execute.py`
  - `titan_core/executor.py`
- Legacy duplicate:
  - `titan_api/dispatcher.py`
  - `tools/executor.py`

### Rules engines
- Active:
  - `titan_core/rules.py`
- Legacy duplicate:
  - `tools/rules.py`

### Frontend chat controllers
- Active:
  - Inline JavaScript inside `titan_ui/index.html`
- Legacy duplicate:
  - `titan_ui/app.js`

### App mounting and static UI serving
- Active:
  - `titan_core/main.py`
- Legacy duplicate:
  - `titan_api/main.py`

### Task and draft persistence
- Active state:
  - Rule proposals exist in `titan_core/rules.py`
  - Active executor does not persist tasks or drafts
- Legacy duplicate:
  - `titan_api/dispatcher.py` can persist `create_task`, `save_memory`, and `draft_email`

## Risk Areas
### Duplicate logic
- There are two backend application architectures:
  - `titan_core/main.py`
  - `titan_api/main.py`
- There are two executor systems:
  - `titan_core/executor.py`
  - `titan_api/dispatcher.py`
- There are two rules systems:
  - `titan_core/rules.py`
  - `tools/rules.py`
- There are two frontend controllers for chat:
  - inline controller in `titan_ui/index.html`
  - `titan_ui/app.js`

### Dead code
- `titan_ui/app.js` appears dead because the active HTML file does not load it
- `tools/controller.py`, `tools/rules.py`, `tools/executor.py`, and `tools/apps.py` appear dead relative to the active app
- `titan_api/schemas.py` appears dead relative to the active app
- `titan_core/json_utils.py` appears unused on the current runtime path

### Partial wiring
- `titan_core/rules.py` can propose `create_task` and `draft_email`, but the active `titan_core/executor.py` cannot execute them
- `titan_core/executor.py` supports `open_url`, but no active proposer currently emits `open_url`
- `titan_core/rules.py` recognizes many app aliases, but the active executor only launches `edge` and `vscode`
- `titan_core/policy.py` allows some action types such as `create_task`, `save_memory`, and `draft_email`, but the active execution layer only implements a subset of the broader intent surface

### Conflicting modules
- `titan_api/main.py` imports `titan_core.brain` and `titan_core.schemas`, which blurs the boundary between the legacy backend and the newer core backend
- The repo has both active and legacy implementations of similar concepts under different package roots, which makes it easy to patch the wrong file
- `titan_ui/index.html` contains the real active UI logic inline, while `titan_ui/app.js` suggests a second frontend control path that is not actually live

### Operational ambiguity
- Developers can easily mistake `titan_api/` for the active backend because it is more feature-complete in some areas, but `titan_core/main.py` is the actual runtime entrypoint named in the current architecture
- The most capable persistence features for tasks, drafts, approvals, and audit logs currently live in the legacy backend, while the visible UI talks to the newer backend that does not expose those same flows

## Summary
If Titan is launched from `titan_core/main.py`, the active system is:
- `titan_core/main.py`
- `titan_core/api/chat.py`
- `titan_core/api/execute.py`
- `titan_core/api/sitrep.py`
- their imported support modules under `titan_core/` and `titan_brain/`
- `titan_ui/index.html`

The main legacy or unused areas are:
- most of `titan_api/`
- `titan_ui/app.js`
- the standalone `tools/` runtime helpers

The biggest architectural risk is not missing code, but split code: Titan currently has one active UI and runtime entrypoint, but multiple overlapping implementations of chat, actions, persistence, and app launching living beside it.
