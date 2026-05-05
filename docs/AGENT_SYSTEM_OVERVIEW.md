# Agent System Overview

## Overview
Titan Agent is a safe planning layer that turns user requests into reviewable actions and multi-step plans. It helps Titan suggest useful next moves while keeping the human in control of execution.

## Action System
Titan proposes actions first and executes only after approval.

- Proposed actions include ids, timestamps, confidence, reason, and lifecycle status.
- `/api/chat` returns actions for the UI to review.
- Execution stays inside the allow-listed backend path.
- Unsupported or future-facing actions can still be proposed without being executed.

## Plan System
Titan can build structured plans for broader requests like “start my day.”

- Plans include a `plan_id`, summary, current step index, next-step message, and action list.
- Each action follows the same schema as standalone proposed actions.
- Plans progress one step at a time through approve, skip, and replace flows.
- Completion happens when no action remains in `pending`.

## Chat Control
Titan supports natural language plan control through chat.

- Approve phrases like `approve next`, `go ahead`, and `continue`
- Skip phrases like `skip this step` and `move past this`
- Replace phrases like `actually ... instead` and `replace`

These chat controls only work when an active plan exists, and they route into the same backend step-control endpoints used by the manual UI buttons.

## Memory + Learning
Titan keeps append-only action history in `data/action_log.json`.

- Proposed, approved, executed, skipped, replaced, cancelled, and failed events are logged
- `agent_memory.py` summarizes recent actions and behavior patterns
- Titan can identify `most_skipped`, `most_replaced`, and `most_approved`
- The suggestion engine uses those patterns to recommend optional step replacements

## Safety Model
Titan is intentionally conservative.

- No auto-execution of proposed actions
- Allow-list only for executable actions
- Full action lifecycle logging
- Step changes like skip and replace stay user-triggered
- Chat-based control detects intent but does not execute directly inside `/api/chat`

## Limitations
The current system is deliberately simple.

- No autonomous execution
- No unrestricted external system control
- Pattern-based suggestions instead of ML or embeddings
- Suggestions are optional and can be ignored
- Behavior learning depends on available local action history
