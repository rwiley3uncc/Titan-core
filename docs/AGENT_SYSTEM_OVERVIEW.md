# Agent System Overview

## Overview
Titan Agent is a guided action layer for the Titan assistant. It turns user requests into reviewable actions and step-by-step plans so the user stays in control.

## Action System
- Titan proposes actions before anything runs.
- Each proposed action includes an action id, timestamp, status, confidence score, and short reason.
- The UI presents actions for approval, cancellation, or plan-based review.
- Executable actions stay behind the backend allow-list.

## Plan System
- Titan can return a multi-step plan for broader requests such as "start my day."
- Plans include a summary, ordered actions, the current step, and a next-step message.
- Steps move forward one at a time through approve, skip, or replace flows.
- A plan is complete when no steps remain in `pending`.

## Chat Control
- Natural language can guide the active plan.
- Users can approve the next step, skip the current step, or replace it through normal chat phrasing.
- Chat control routes into the same backend endpoints used by the manual plan buttons.

## Memory and Suggestions
- Titan keeps append-only lifecycle history in `data/action_log.json`.
- `agent_memory.py` summarizes recent behavior and common patterns such as most skipped or most approved actions.
- When behavior history is strong enough, Titan can suggest an optional replacement for the current plan step.
- Suggestions include a confidence score and a short explanation.

## Safety Model
- No auto-execution of proposed actions
- Allow-list only for executable actions
- Approval required before execution
- Full lifecycle logging for actions and plan changes
- Plan progression is limited to one step at a time

## Limitations
- No autonomous execution
- No unrestricted external system control
- Suggestions are pattern-based, not ML-driven
- Behavior-aware suggestions depend on available local history
