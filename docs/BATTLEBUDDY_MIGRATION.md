# Titan BattleBuddy Migration Notes

Titan-core is being renamed in stages to **Titan BattleBuddy**.

Current state:

- `titan_battlebuddy` is the new public application namespace.
- `titan_core` still exists temporarily for compatibility.
- `titan_core.main` forwards to `titan_battlebuddy.main`.
- existing URLs remain the same:
  - `/health`
  - `/api/chat`
  - `/api/sitrep`
  - `/ui/index.html`
- Titan-AI is now the AI engine and orchestration layer.
- Titan BattleBuddy is the operational assistant, controller, and UI gateway.

Compatibility notes:

- Old startup still works:
  - `python -m uvicorn titan_core.main:app --reload`
- New startup is available:
  - `python -m uvicorn titan_battlebuddy.main:app --reload`
- Old PowerShell launchers still work and forward to the new BattleBuddy launcher.

This is a staged migration. The `titan_core` namespace should be treated as
temporary compatibility glue until more internal modules are moved behind the
BattleBuddy namespace.

