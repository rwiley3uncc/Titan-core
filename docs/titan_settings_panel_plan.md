# Titan Settings Panel Plan

## Purpose
Add a future Settings button and modal to Titan so the user can manage assistant configuration in one clear place.

This document is a design/spec only. It does not implement UI or backend changes.

## Goals
- Give the user one place to manage Titan configuration
- Keep sensitive data and permissions explicit
- Make source access visible and understandable
- Preserve Titan's grounding rules
- Support future caregiver-aware workflows without exposing private data by default

## Current Context
Titan already has:
- browser-side voice controls in `titan_ui/index.html`
- environment-based calendar feed settings in `titan_core/config.py`
- sitrep generation from configured Canvas and Outlook ICS feeds in `titan_core/api/sitrep.py`
- explicit no-guessing behavior in personal-assistant responses

The Settings panel should eventually become the user-facing configuration layer above those systems.

## Proposed Entry Point
### UI entry
- Add a `Settings` button in the top bar or conversation panel
- Button opens a modal, not a new page
- Modal should be usable on desktop and mobile

### Modal design
- Title: `Titan Settings`
- Sections or tabs:
  - `Calendar Sources`
  - `Caregiver Access`
  - `Voice`
  - `Privacy & Grounding`
- Footer actions:
  - `Save`
  - `Cancel`
  - optional `Test Voice`
  - optional `Refresh Sources`

## Section 1: Calendar Sources
### User goals
- Add or edit calendar feed URLs
- Enable or disable each source
- Label sources by purpose and owner
- Understand which feeds power sitrep and schedule features

### Proposed settings model
Each calendar source record should support:
- `source_id`
- `label`
- `kind`
  - examples: `School`, `Personal`, `Caregiver`
- `url`
- `enabled`
- `read_only`
- `owner_role`
  - examples: `self`, `caregiver`
- `last_sync_status`
- `last_sync_at`

### Example UI fields
- Source label
- Source type dropdown
  - `School`
  - `Personal`
  - `Wife/Caregiver`
- Feed URL input
- Enabled toggle
- Read-only badge or note
- Last checked status

### Example actions
- `Add Source`
- `Edit`
- `Disable`
- `Remove`
- `Test Feed`

### Validation rules
- Feed URLs must be explicit and user-provided
- Titan should never infer or auto-connect calendar sources
- Disabled feeds should not appear in sitrep or schedule calculations
- Failed feeds should show an error state, not silent fallback

### Future backend implications
- Move from env-only feed settings toward persisted per-source records
- Likely add a settings store or config API layer
- Sitrep builder should read enabled sources only

## Section 2: Caregiver Access
### User goals
- Allow trusted caregiver calendar access when explicitly approved
- Keep caregiver data clearly separated from the user’s own data
- Prevent accidental exposure of private information

### Core principles
- No caregiver access by default
- Explicit opt-in only
- Clear separation between:
  - `view-only access`
  - `edit access`
- Titan should explain what caregiver-linked data may affect:
  - sitrep
  - schedule awareness
  - reminders
  - shared task visibility

### Proposed access model
Each caregiver permission record should support:
- `person_label`
  - example: `Wife/Caregiver`
- `relationship`
- `calendar_sources_allowed`
- `view_permission`
- `edit_permission`
- `task_visibility_scope`
- `approved_at`
- `approved_by`

### Recommended UI copy
- `Allow Titan to read this caregiver calendar for planning support`
- `View-only means Titan can see timing information but cannot modify anything`
- `Edit access should remain off unless explicitly enabled later`

### Access levels
#### View-only
- Titan may read shared timing or availability data
- Titan may use that data in scheduling logic
- Titan may not modify caregiver sources

#### Edit access
- Not recommended for initial release
- Should remain disabled in MVP
- Requires a stronger confirmation flow if ever added

### Privacy rules
- No private caregiver data should be shown or used unless the user explicitly grants access
- Titan should display exactly which caregiver-linked sources are connected
- Titan should distinguish:
  - `connected but disabled`
  - `connected and readable`
  - `editable`

## Section 3: Voice
### User goals
- Choose the read-aloud voice
- Tune playback quality and comfort
- Persist those preferences across sessions

### Settings to expose
- `voice`
- `rate`
- `pitch`
- `volume`

### Recommended UI elements
- Voice dropdown
- Rate slider
- Pitch slider
- Volume slider
- `Test Voice` button

### Suggested defaults
- Rate: `0.95`
- Pitch: `1.0`
- Volume: `1.0`

### Behavioral notes
- Prefer natural English voices when available
- Fall back to browser default if no better voice exists
- Keep `Read Sitrep` and `Stop Voice` behavior unchanged

### Persistence
- Short term:
  - browser `localStorage`
- Longer term:
  - optional synced user preferences if Titan gains account-level settings storage

## Section 4: Privacy & Grounding
### User goals
- See what Titan is connected to
- Understand what Titan can access
- Understand what Titan cannot access
- See a reminder that Titan does not guess when data is missing

### Proposed UI blocks
#### Connected Sources
Show:
- Canvas feed connected or not
- Outlook feed connected or not
- personal task store connected
- caregiver-linked sources connected or not
- browser-only voice features

#### What Titan Can Access
Examples:
- configured ICS feed items
- saved Titan tasks
- browser speech synthesis voices
- user-provided development file uploads during the current session

#### What Titan Cannot Access
Examples:
- inbox/email unless explicitly integrated
- calendars without configured feeds
- caregiver/private sources without permission
- files not uploaded or provided
- hidden/private systems Titan has not been connected to

#### Grounding Reminder
Recommended copy:
- `Titan answers from connected data sources and the information you provide.`
- `If data is missing or unverified, Titan should say: "I don't know based on the information I have."`

### Security and trust cues
- Use plain language
- Avoid implying access Titan does not actually have
- Prefer explicit status labels:
  - `Connected`
  - `Disabled`
  - `Missing`
  - `View-only`
  - `Edit access not enabled`

## UX Structure
### Recommended layout
- Modal with left-side navigation on desktop
- Stacked section cards on mobile
- Save state per section

### Suggested modal sections
1. `Calendar Sources`
2. `Caregiver Access`
3. `Voice`
4. `Privacy & Grounding`

### Suggested feedback states
- `Saved`
- `Validation error`
- `Connection test failed`
- `Permission required`

## Data Model Ideas
### Settings container
A future persisted settings object could include:
- `calendar_sources`
- `caregiver_permissions`
- `voice_preferences`
- `privacy_preferences`

### Voice preferences
- `voice_name`
- `rate`
- `pitch`
- `volume`

### Privacy preferences
- `show_source_status`
- `show_grounding_reminder`
- `allow_caregiver_context`

## API and Storage Considerations
### Near-term option
- Keep voice settings browser-side
- Add backend settings endpoints later for calendar and caregiver management

### Future API candidates
- `GET /api/settings`
- `POST /api/settings/calendar-sources`
- `POST /api/settings/caregiver-access`
- `POST /api/settings/voice`
- `GET /api/settings/privacy`

### Storage options
- JSON-backed settings store for MVP
- database-backed settings later if multi-user or permissions grow more complex

## Safety Requirements
- No private source should be connected automatically
- No caregiver data should be visible without explicit permission
- View-only and edit access must be clearly separated
- Titan must continue to honor the no-guessing rule
- Settings UI must reflect real connected capabilities, not aspirational ones

## Implementation Phasing
### Phase 1
- Add Settings button and modal shell
- Move current voice settings into the modal
- Add Privacy & Grounding overview

### Phase 2
- Add editable calendar source list
- Add enable/disable controls
- Add source labels and test status

### Phase 3
- Add caregiver access records and explicit permission flow
- Keep caregiver support view-only at first

### Phase 4
- Add stronger persistence and account-scoped settings if needed

## Open Questions
- Should calendar source settings remain global or become per-user?
- Should caregiver-linked sources be visible in sitrep by default once approved, or require a separate include toggle?
- Should task sources eventually appear in Calendar Sources, or remain a separate internal source?
- Should voice preferences stay browser-local or sync with a future Titan account?

## Recommended First Slice
For the first real implementation, the best low-risk slice is:
- add a `Settings` button
- open a modal
- move existing voice controls into it
- add a read-only `Privacy & Grounding` status panel

That delivers visible value immediately and creates the structure needed for calendar and caregiver configuration later.
