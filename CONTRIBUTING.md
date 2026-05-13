<!-- Copyright (c) 2026 Ron Wiley. All rights reserved. -->

# Contributing

Contributions to Titan-core must preserve Titan's platform philosophy.

## Required contribution rules

- preserve human authority first
- preserve validation before orchestration
- preserve constrained execution
- preserve modular runtime separation
- preserve explicit approval boundaries
- preserve sandbox-first remediation posture
- preserve no-hidden-autonomy behavior
- preserve fail-closed behavior

## Special review areas

Any change affecting these areas requires explicit review:

- execution paths
- approvals
- remediation
- orchestration
- validation baselines
- runtime boundaries
- cross-runtime integration

## Contribution hygiene

- run relevant tests and validation before merge
- do not describe future or planned capabilities as currently implemented
- do not commit local secrets or artifacts
- do not commit `.env`, DB files, logs, JSONL runtime streams, screenshots, exports, or validation outputs
- do not weaken BattleBuddy verified-knowledge fail-closed behavior

## Scope note

This repository is part of a broader local-first AI operations platform. BattleBuddy-specific assistant wording is acceptable here when it refers to the interaction/runtime boundary rather than the whole platform identity.
