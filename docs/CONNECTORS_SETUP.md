# Connector Setup

## Environment
Copy `.env.example` to `.env` and fill in the values.

Required for current sitrep endpoint:
- `TITAN_CANVAS_ICS_URL` - private UNC Charlotte Canvas ICS feed URL
- `TITAN_OUTLOOK_CALENDAR_EMAIL` - Outlook account Titan should target first

Optional:
- `TITAN_OWNER_USERNAME`
- `TITAN_SITREP_TIME`
- `TITAN_STUDY_BLOCK_MINUTES`

## Current status
- Canvas ICS is wired for import in the sitrep endpoint
- Outlook is only configured as a target account for now; live availability sync still needs Microsoft calendar API integration
- Weather can be passed into the sitrep endpoint for now and later replaced with a live weather connector

## Security
- Do not commit the Canvas ICS URL to GitHub
- Treat the feed URL like a password and rotate/regenerate it if exposed
