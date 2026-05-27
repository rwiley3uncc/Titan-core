# Titan Course Workspace

This folder is the local-first course-material workspace for the minimum `student_ops` slice.

Recommended layout:

- `data/courses/<course_id>/course_manifest.json`
- `data/courses/<course_id>/notes/`
- `data/courses/<course_id>/slides/`
- `data/courses/<course_id>/assignments/`

Rules:

- keep course materials local
- treat course files as read-only source material for now
- do not expect automatic LMS ingestion or hidden background indexing
- prefer `.md`, `.txt`, and `.json` for the current retrieval MVP
- keep graded submissions and answer keys out unless you intentionally need them for review boundaries

Current retrieval scope:

- only `source_files` listed in `course_manifest.json` are searchable
- only `.md`, `.txt`, and `.json` are supported in this MVP
- unsupported file types are ignored by retrieval and should fail validation honestly

The validators check that listed `source_files` stay within the course folder, exist locally, and use a supported retrieval extension.
