<!-- Copyright (c) 2026 Ron Wiley. All rights reserved. -->

# Release Checklist

- confirm repository license posture is still correct
- run tests and validation for Titan-core / BattleBuddy
- run a secret scan
- confirm no `.env` files are staged
- confirm no DB files, logs, JSONL streams, or runtime artifacts are staged
- confirm no screenshots or validation artifacts are staged
- confirm no local absolute paths remain in public-facing release docs unless intentionally internal
- confirm no misleading autonomy or remediation claims remain
- confirm BattleBuddy verified knowledge still fails closed
- confirm live apply remains blocked at the platform level
- confirm sandbox-only remediation remains enforced at the platform level
- confirm approval gates remain intact
- confirm Titan-AI remains library-only
- confirm docs still match actual runtime behavior
