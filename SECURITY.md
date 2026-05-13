<!-- Copyright (c) 2026 Ron Wiley. All rights reserved. -->

# Security Policy

Titan is a local-first AI operations platform. Titan-core currently hosts the active Titan BattleBuddy runtime and the transitional `titan_core` compatibility namespace.

## Reporting vulnerabilities

Report suspected vulnerabilities privately to the maintainer for coordinated review.

Do not publicly disclose exploitable issues before the maintainer has had a reasonable opportunity to review, reproduce, and scope the issue.

## Prohibited security regressions

Do not submit changes that:

- enable hidden autonomy
- enable autonomous execution
- enable autonomous live remediation
- bypass approval boundaries
- weaken fail-closed behavior
- collapse runtime separation
- turn Titan-AI into a runtime authority

## Current safety invariants

- no autonomous live remediation
- sandbox-first remediation
- explicit approval boundaries
- constrained execution
- fail-closed behavior
- runtime separation
- Titan-AI is a library layer, not a runtime

## Scope note

This file describes current engineering and disclosure expectations. It is not legal advice and does not create a warranty or guarantee.
