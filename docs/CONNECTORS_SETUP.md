# Connector Setup

## Environment
Copy `.env.example` to `.env` and fill in the values.

Required for the combined school + life sitrep:
- `TITAN_CANVAS_ICS_URL` - private UNC Charlotte Canvas ICS feed URL
- `TITAN_OUTLOOK_CALENDAR_EMAIL` - Outlook account Titan should target first
- `TITAN_OUTLOOK_ICS_URL` - published Outlook ICS feed for life calendar items

Optional:
- `TITAN_OWNER_USERNAME`
- `TITAN_SITREP_TIME`
- `TITAN_STUDY_BLOCK_MINUTES`

## Current status
- Canvas ICS is wired for school items
- Outlook ICS is wired for life calendar items
- The dashboard UI reads `/api/sitrep`
- Voice output uses browser speech synthesis as the first MVP voice path

## Security
- Do not commit the Canvas or Outlook ICS URLs to GitHub
- Treat both feed URLs like passwords and rotate them if exposed
