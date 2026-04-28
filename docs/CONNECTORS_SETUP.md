# Connector Setup

## Environment
Copy `.env.example` to `.env` and fill in the values.

Required for the combined school + life sitrep:
- `TITAN_CANVAS_ICS_URL` - private UNC Charlotte Canvas ICS feed URL
- `TITAN_OUTLOOK_CALENDAR_EMAIL` - Outlook account Titan should target first
- `TITAN_OUTLOOK_ICS_URL` - published Outlook ICS feed for life calendar items

Optional multi-calendar configuration:
- `TITAN_CALENDAR_SOURCES_JSON` - JSON array of calendar source objects with `name`, `type`, `url`, and optional `enabled`
- `data/calendar_sources.json` - saved calendar source list used by the settings API; Titan loads all enabled entries

Example multi-calendar env value:
- `[{"name":"School Calendar","type":"canvas","url":"https://example.com/school.ics","enabled":true},{"name":"Personal Calendar","type":"outlook","url":"https://example.com/personal.ics","enabled":true}]`

Optional:
- `TITAN_OWNER_USERNAME`
- `TITAN_SITREP_TIME`
- `TITAN_STUDY_BLOCK_MINUTES`

## Current status
- Legacy single Canvas and Outlook ICS settings still work
- Titan can also load multiple enabled calendars from `TITAN_CALENDAR_SOURCES_JSON`
- Titan loads all enabled saved calendar sources from `data/calendar_sources.json`
- Calendar events from every successful source are merged into one sitrep timeline
- The dashboard UI reads `/api/sitrep`
- Voice output uses browser speech synthesis as the first MVP voice path

## Security
- Do not commit the Canvas or Outlook ICS URLs to GitHub
- Treat both feed URLs like passwords and rotate them if exposed
