from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from titan_core.titan_ai_imports import enable_titan_ai_imports
from titan_core.titan_shared_imports import ensure_titan_shared_on_path

enable_titan_ai_imports()
ensure_titan_shared_on_path()

from titan_ai.ai_types import AIMessage, AIRequest
from titan_ai.course_qa_service import answer_course_question
from titan_ai.prompts import build_system_prompt
from titan_core.chat_mode import is_personal_assistant_mode, safe_mode
from titan_core.course_manifest import list_course_manifests, validate_course_manifest_record
from titan_core.policy import apply_policy
from titan_core.schemas import BrainInput, BrainOutput, ChatMessage, ProposedAction
from titan_battlebuddy.main import app
from titan_shared.course_document_store import (
    ingest_course_document,
    load_document_chunks,
    search_course_documents,
    store_uploaded_course_document,
)
from titan_shared.runtime_validation import print_validation_report, python_runtime_summary


ROOT = Path(__file__).resolve().parent
STUDENT_MODE_CONFIG_PATH = ROOT / "configs" / "student_mode_config.json"
COURSES_ROOT = ROOT / "data" / "courses"
STUDENT_UI_PATH = ROOT / "titan_ui" / "index.html"
EXPECTED_EXTENSIONS = [".docx", ".pdf", ".md", ".txt"]
EXPECTED_STUDENT_DOCUMENT_ROUTES = (
    ("GET", "/api/student-documents"),
    ("POST", "/api/student-documents/upload"),
)


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_sample_pdf_bytes(page_lines: list[list[str]]) -> bytes:
    object_ids = {
        "catalog": 1,
        "pages": 2,
        "font": 3,
    }
    next_object_id = 4
    page_entries: list[tuple[int, int, list[str]]] = []
    for lines in page_lines:
        page_id = next_object_id
        content_id = next_object_id + 1
        next_object_id += 2
        page_entries.append((page_id, content_id, lines))

    objects: list[tuple[int, bytes]] = []
    kids_refs = " ".join(f"{page_id} 0 R" for page_id, _, _ in page_entries)
    objects.append((object_ids["catalog"], b"<< /Type /Catalog /Pages 2 0 R >>"))
    objects.append((object_ids["pages"], f"<< /Type /Pages /Kids [{kids_refs}] /Count {len(page_entries)} >>".encode("ascii")))
    objects.append((object_ids["font"], b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))

    for page_id, content_id, lines in page_entries:
        page_object = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        operations = ["BT", "/F1 12 Tf", "14 TL", "72 720 Td"]
        for index, line in enumerate(lines):
            if index > 0:
                operations.append("T*")
            operations.append(f"({_escape_pdf_text(line)}) Tj")
        operations.append("ET")
        stream_payload = "\n".join(operations).encode("latin-1")
        content_object = (
            f"<< /Length {len(stream_payload)} >>\nstream\n".encode("ascii")
            + stream_payload
            + b"\nendstream"
        )
        objects.append((page_id, page_object))
        objects.append((content_id, content_object))

    objects.sort(key=lambda item: item[0])
    output = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for object_id, payload in objects:
        offsets[object_id] = len(output)
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(payload)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    max_object_id = max(offsets)
    output.extend(f"xref\n0 {max_object_id + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for object_id in range(1, max_object_id + 1):
        output.extend(f"{offsets[object_id]:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {max_object_id + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


def _build_sample_docx_bytes(paragraphs: list[str]) -> bytes:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    document_relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""
    paragraph_xml = []
    for paragraph in paragraphs:
        escaped = (
            paragraph.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        paragraph_xml.append(f"<w:p><w:r><w:t xml:space=\"preserve\">{escaped}</w:t></w:r></w:p>")
    document_xml = (
        """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>"""
        + "".join(paragraph_xml)
        + """<w:sectPr/></w:body>
</w:document>"""
    )

    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", document_relationships)
    return buffer.getvalue()


def _validate_student_mode_config() -> list[str]:
    issues: list[str] = []

    if not STUDENT_MODE_CONFIG_PATH.exists():
        return [f"Missing student mode config: {STUDENT_MODE_CONFIG_PATH}"]

    try:
        payload = json.loads(STUDENT_MODE_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"Invalid student mode config JSON: {exc}"]

    if not isinstance(payload, dict):
        return ["Student mode config must be a JSON object."]

    if str(payload.get("mode_id") or "").strip() != "student_ops":
        issues.append("student mode config must declare mode_id='student_ops'.")

    behavior_rules = payload.get("behavior_rules")
    if not isinstance(behavior_rules, dict):
        issues.append("student mode config must include a behavior_rules object.")
    else:
        required_true_flags = (
            "teach_and_explain",
            "allow_concept_guidance",
            "require_source_honesty",
            "require_missing_info_disclosure",
            "forbid_direct_graded_work_completion",
            "forbid_hidden_tool_execution",
            "forbid_autonomous_remediation",
            "forbid_live_apply",
        )
        for flag in required_true_flags:
            if behavior_rules.get(flag) is not True:
                issues.append(f"student mode config must set behavior_rules.{flag}=true.")

    source_policy = payload.get("source_policy")
    if not isinstance(source_policy, dict):
        issues.append("student mode config must include a source_policy object.")
    else:
        for flag in ("local_first", "read_only_course_materials", "cite_sources_when_available", "no_hidden_web_calls"):
            if source_policy.get(flag) is not True:
                issues.append(f"student mode config must set source_policy.{flag}=true.")

    retrieval_policy = payload.get("retrieval_policy")
    if not isinstance(retrieval_policy, dict):
        issues.append("student mode config must include a retrieval_policy object.")
    else:
        for flag in ("enabled", "local_only", "read_only"):
            if retrieval_policy.get(flag) is not True:
                issues.append(f"student mode config must set retrieval_policy.{flag}=true.")
        if retrieval_policy.get("persistent_background_indexing") is not False:
            issues.append("student mode config must set retrieval_policy.persistent_background_indexing=false.")
        supported_extensions = retrieval_policy.get("supported_extensions")
        if supported_extensions != EXPECTED_EXTENSIONS:
            issues.append(
                "student mode config must declare supported_extensions ['.docx', '.pdf', '.md', '.txt']."
            )

    return issues


def _validate_mode_aliases() -> list[str]:
    issues: list[str] = []
    if safe_mode("student_ops") != "student_ops":
        issues.append("safe_mode('student_ops') did not preserve the student_ops mode.")
    if not is_personal_assistant_mode("student_ops"):
        issues.append("student_ops must route through the personal-grounded assistant path.")
    return issues


def _validate_policy_behavior() -> list[str]:
    issues: list[str] = []
    inp = BrainInput(
        user_id=1,
        role="student",
        mode="student_ops",
        messages=[ChatMessage(role="user", content="This is my quiz. Just give me the answer.")],
    )
    out = BrainOutput(
        reply="The answer is 42.",
        proposed_actions=[ProposedAction(type="draft_email", label="should be removed")],
    )
    guarded = apply_policy(inp, out)
    if "can't help with answers to an active quiz" not in guarded.reply.lower():
        issues.append("student_ops policy did not enforce the quiz/exam refusal path.")
    if guarded.proposed_actions:
        issues.append("student_ops policy should clear proposed actions during quiz/exam refusal.")
    return issues


def _validate_prompt_behavior() -> list[str]:
    issues: list[str] = []
    prompt = build_system_prompt(
        AIRequest(
            role="student",
            mode="student_ops",
            tools=[],
            messages=[AIMessage(role="user", content="Help me study.")],
        )
    ).lower()
    for marker in (
        "student operations assistant",
        "do not directly complete graded work",
        "use only verified source context",
        "do not perform hidden tool use",
        "name the course/source files you relied on",
    ):
        if marker not in prompt:
            issues.append(f"student_ops prompt is missing required guidance marker: {marker}")
    return issues


def _validate_course_manifests() -> list[str]:
    issues: list[str] = []
    if not COURSES_ROOT.exists():
        return [f"Missing courses root: {COURSES_ROOT}"]

    for record in list_course_manifests(COURSES_ROOT):
        issues.extend(validate_course_manifest_record(record))

    return issues


def _validate_student_workspace_layout() -> list[str]:
    issues: list[str] = []
    if not STUDENT_UI_PATH.exists():
        return [f"Missing BattleBuddy UI file: {STUDENT_UI_PATH}"]

    markup = STUDENT_UI_PATH.read_text(encoding="utf-8")
    required_markers = (
        'html,\nbody {\n  margin: 0;\n  padding: 0;\n  min-height: 100%;\n  overflow-x: hidden;\n  overflow-y: auto;',
        'body {\n  display: flex;\n  flex-direction: column;\n  min-height: 100vh;',
        '.container {\n  max-width: 100%;\n  margin: 0;\n  padding: 8px 10px 10px;\n  flex: 1 1 auto;\n  min-height: 0;\n  overflow: visible;\n  display: flex;\n  flex-direction: column;',
        'id="sitrepStrip"',
        'class="conversation-composer"',
        'id="msg"',
        'id="sendBtn"',
        'id="studentDocFileInput"',
        'student-documents-panel',
        'class="secondary-panels"',
        '.dashboard {\n  display: flex;\n  flex-direction: column;',
        '.primary-row {\n  display: grid;\n  grid-template-columns: minmax(0, 1.7fr) minmax(300px, 0.92fr);\n  gap: 10px;\n  flex: 0 0 auto;\n  min-height: 0;\n  align-items: stretch;\n  overflow: visible;',
        '.conversation-panel {\n  min-height: clamp(520px, 62vh, 760px);\n  height: auto;\n  display: flex;\n  flex-direction: column;\n  flex: 0 0 auto;\n  overflow: visible;',
        '.conversation-shell {\n  display: flex;\n  flex-direction: column;\n  min-height: 0;\n  height: auto;\n  flex: 1 1 auto;\n  overflow: visible;',
        '#chat {\n  flex: 1 1 auto;\n  min-height: clamp(260px, 34vh, 420px);\n  height: auto;\n  max-height: none;\n  overflow-y: auto;\n  overflow-x: hidden;',
        '.conversation-composer {\n  display: grid;\n  gap: 10px;\n  margin-top: 10px;\n  padding-top: 10px;\n  border-top: 1px solid rgba(106, 157, 199, 0.14);\n  background: linear-gradient(180deg, rgba(9, 23, 37, 0), rgba(9, 23, 37, 0.92) 26%, rgba(9, 23, 37, 0.98));\n  flex: 0 0 auto;\n  min-height: 210px;\n  overflow: visible;',
        '.student-documents-list {\n  display: grid;\n  flex: 1 1 auto;\n  min-height: 0;\n  gap: 8px;\n  margin-top: 10px;\n  max-height: none;\n  overflow-y: auto;',
    )
    for marker in required_markers:
        if marker not in markup:
            issues.append(f"BattleBuddy UI is missing required Batch 39 workspace marker: {marker}")

    banned_markers = (
        'id="workspaceMode"',
        "WORKSPACE_MODE_STORAGE_KEY",
        "SITREP_COLLAPSED_STORAGE_KEY",
        "function applyWorkspaceMode()",
        "function toggleSitrepCollapsed()",
        'id="sitrepPanel"',
    )
    for marker in banned_markers:
        if marker in markup:
            issues.append(f"BattleBuddy UI still contains removed workspace-mode marker: {marker}")

    conversation_index = markup.find('class="panel conversation-panel"')
    documents_index = markup.find('id="studentDocumentSection"')
    sitrep_index = markup.find('id="sitrepStrip"')
    primary_row_index = markup.find('class="primary-row"')
    secondary_index = markup.find('class="secondary-panels"')
    if conversation_index == -1 or documents_index == -1:
        issues.append("BattleBuddy UI is missing the conversation panel or student documents panel.")
    elif sitrep_index == -1:
        issues.append("BattleBuddy UI is missing the compact sitrep strip.")
    elif primary_row_index == -1:
        issues.append("BattleBuddy UI is missing the two-column primary row.")
    elif not (primary_row_index < conversation_index < secondary_index):
        issues.append("BattleBuddy UI no longer keeps the conversation panel inside the primary row and before the secondary cards.")
    elif documents_index < conversation_index:
        issues.append("BattleBuddy UI no longer places the student documents panel after the conversation panel.")
    elif sitrep_index < documents_index:
        issues.append("BattleBuddy UI no longer keeps the sitrep strip below the student documents panel.")
    elif secondary_index != -1 and secondary_index < sitrep_index:
        issues.append("BattleBuddy UI no longer keeps the compact secondary panels below the course document panel.")

    composer_index = markup.find('class="conversation-composer"')
    textarea_index = markup.find('id="msg"')
    send_button_index = markup.find('id="sendBtn"')
    documents_panel_index = markup.find('id="studentDocumentSection"')
    chat_index = markup.find('id="chat"')
    if composer_index == -1 or textarea_index == -1 or send_button_index == -1:
        issues.append("BattleBuddy UI is missing the conversation composer, chat textarea, or send button.")
    else:
        if chat_index == -1:
            issues.append("BattleBuddy UI is missing the chat transcript container.")
        elif not (chat_index < textarea_index):
            issues.append("BattleBuddy UI no longer keeps the textarea after the transcript in DOM order.")
        if not (composer_index < textarea_index < documents_panel_index):
            issues.append("BattleBuddy UI no longer keeps the chat textarea above the student documents panel.")
        if not (composer_index < send_button_index < documents_panel_index):
            issues.append("BattleBuddy UI no longer keeps the send button above the student documents panel.")
        if secondary_index != -1 and not (documents_panel_index < secondary_index):
            issues.append("BattleBuddy UI no longer keeps the compact secondary cards after the course document panel.")
        if primary_row_index != -1 and not (primary_row_index < documents_panel_index):
            issues.append("BattleBuddy UI no longer keeps the student documents panel inside the primary row.")

    return issues


def _route_table_snapshot() -> list[dict[str, object]]:
    route_entries: list[dict[str, object]] = []
    for route in app.routes:
        path = str(getattr(route, "path", "") or "").strip()
        methods = sorted(str(method).strip() for method in (getattr(route, "methods", None) or []) if str(method).strip())
        if not path:
            continue
        route_entries.append(
            {
                "path": path,
                "methods": methods,
            }
        )
    return sorted(route_entries, key=lambda item: (str(item["path"]), ",".join(item["methods"])))


def _validate_battlebuddy_route_registration() -> list[str]:
    issues: list[str] = []
    registered_routes = {
        (method, str(route["path"]))
        for route in _route_table_snapshot()
        for method in route["methods"]
    }
    for method, path in EXPECTED_STUDENT_DOCUMENT_ROUTES:
        if (method, path) not in registered_routes:
            issues.append(
                f"BattleBuddy route table is missing {method} {path}."
            )
    return issues


def _validation_detail(response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, dict):
            return str(detail.get("message") or detail.get("status") or payload)
        if detail is not None:
            return str(detail)
    return str(payload)


def _validate_battlebuddy_student_documents() -> list[str]:
    issues: list[str] = []
    temp_root = Path(tempfile.mkdtemp(prefix="titan-student-mode-validation-"))
    docs_root = temp_root / "course_documents"
    previous_docs_root = os.environ.get("TITAN_COURSE_DOCUMENTS_DIR")
    os.environ["TITAN_COURSE_DOCUMENTS_DIR"] = str(docs_root)

    try:
        seed_same_course_path = temp_root / "seed_itsc_2181_notes.md"
        seed_same_course_path.write_text(
            (
                "# Example ITSC 2181 Notes\n"
                "This example file mentions attendance in a generic demo context.\n"
            ),
            encoding="utf-8",
        )
        ingest_course_document(
            str(seed_same_course_path),
            course_tag="ITSC 2181",
            document_category="lecture_notes",
            source_kind="seed_example",
        )

        seed_demo_course_path = temp_root / "demo_itsc_9999_syllabus.md"
        seed_demo_course_path.write_text(
            (
                "# DEMO-101 Syllabus\n"
                "Attendance is required for the demo course and makeup work is limited.\n"
            ),
            encoding="utf-8",
        )
        ingest_course_document(
            str(seed_demo_course_path),
            course_tag="DEMO-101",
            document_category="syllabus",
            source_kind="seed_example",
        )

        with TestClient(app) as client:
            seed_response = client.post("/seed")
            if seed_response.status_code != 200:
                issues.append(
                    f"BattleBuddy seed endpoint returned HTTP {seed_response.status_code}: {_validation_detail(seed_response)}"
                )
                return issues

            upload_response = client.post(
                "/api/student-documents/upload",
                data={
                    "course_tag": "ITSC 2181",
                    "document_category": "syllabus",
                },
                files={
                    "file": (
                        "itsc2181_syllabus.pdf",
                        _build_sample_pdf_bytes(
                            [
                                [
                                    "ITSC 2181 Syllabus",
                                    "Attendance is required for every class meeting.",
                                ],
                                [
                                    "Late work is accepted for up to three days with a grade penalty.",
                                    "Office hours are posted each Monday.",
                                ],
                            ]
                        ),
                        "application/pdf",
                    )
                },
            )
            if upload_response.status_code != 200:
                issues.append(
                    f"BattleBuddy student document upload endpoint returned HTTP {upload_response.status_code}: {_validation_detail(upload_response)}"
                )
                return issues

            upload_payload = upload_response.json()
            record = upload_payload.get("record")
            if not isinstance(record, dict):
                issues.append("BattleBuddy student document upload endpoint did not return a structured document record.")
                return issues
            if str(record.get("course_tag") or "") != "ITSC 2181":
                issues.append("BattleBuddy student document upload endpoint did not preserve the uploaded course tag.")
            if str(record.get("document_category") or "") != "syllabus":
                issues.append("BattleBuddy student document upload endpoint did not preserve the uploaded document category.")
            if str(record.get("file_type") or "") != "pdf":
                issues.append("BattleBuddy student document upload endpoint did not preserve the PDF file type.")
            if str(record.get("source_kind") or "") != "user_upload":
                issues.append("BattleBuddy student document upload endpoint did not mark the document as a user_upload.")
            if not str(record.get("ingestion_status") or "").startswith("ready:"):
                issues.append("BattleBuddy student document upload endpoint did not report a ready PDF extraction status.")
            stored_source_path = Path(str(record.get("source_path") or ""))
            if not stored_source_path.exists():
                issues.append("BattleBuddy student document upload endpoint did not store the selected file locally.")
            elif docs_root not in stored_source_path.parents and stored_source_path != docs_root:
                issues.append("BattleBuddy student document upload stored the file outside the allowlisted local course document workspace.")
            chunks = load_document_chunks(str(record.get("document_id") or ""))
            if not chunks:
                issues.append("BattleBuddy student document upload did not generate any chunks for the PDF syllabus.")
                return issues
            if not any("Late work is accepted" in chunk.content for chunk in chunks):
                issues.append("BattleBuddy student document upload did not extract real syllabus text from the PDF.")
            if not any(chunk.page_number == 2 for chunk in chunks):
                issues.append("BattleBuddy student document upload did not preserve PDF page numbers in chunk metadata.")

            ranked_results = search_course_documents(
                "What does the ITSC 2181 syllabus say about late work?",
                scope="chunks",
                limit=5,
            )
            if not ranked_results:
                issues.append("Course document search did not return any ranked results for the uploaded syllabus query.")
                return issues
            top_result = ranked_results[0]
            if str(top_result.get("filename") or "") != "itsc2181_syllabus.pdf":
                issues.append("Uploaded PDF syllabus was not ranked ahead of seed/example material.")
            if str(top_result.get("course_tag") or "") != "ITSC 2181":
                issues.append("Exact course tag match did not outrank unrelated course material.")
            if int(top_result.get("page_number") or 0) != 2:
                issues.append("PDF search results did not preserve the expected page number for the late-work match.")
            if any(
                str(item.get("source_kind") or "") == "seed_example"
                and str(item.get("course_tag") or "") == "ITSC 2181"
                for item in ranked_results
            ):
                issues.append("Seed/example documents were not excluded when matching uploaded documents existed for the selected course.")

            upload_answer = answer_course_question("What does the ITSC 2181 syllabus say about late work?")
            answer_payload = upload_answer.get("answer")
            if not isinstance(answer_payload, dict):
                issues.append("Course Q&A did not return a structured answer payload for the uploaded syllabus query.")
                return issues
            evidence = answer_payload.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                issues.append("Course Q&A did not attach evidence for the uploaded syllabus query.")
                return issues
            first_evidence = evidence[0]
            if not isinstance(first_evidence, dict) or str(first_evidence.get("filename") or "") != "itsc2181_syllabus.pdf":
                issues.append("Course Q&A did not prioritize the uploaded PDF syllabus evidence.")
            if int(first_evidence.get("page_number") or 0) != 2:
                issues.append("Course Q&A did not preserve the PDF page number in attached evidence.")
            if any(str(item.get("source_kind") or "") != "user_upload" for item in evidence if isinstance(item, dict)):
                issues.append("Course Q&A mixed seed/example evidence into a query that had matching uploaded course documents.")
            if "page 2" not in str(answer_payload.get("answer_text") or "").lower():
                issues.append("Course Q&A answer text did not cite the extracted PDF page number.")

            placeholder_record = store_uploaded_course_document(
                "broken_itsc2181_syllabus.pdf",
                b"%PDF-1.4\nbroken\n%%EOF",
                course_tag="BROKEN-101",
                document_category="syllabus",
            ).get("record")
            if placeholder_record is None:
                issues.append("Broken PDF ingestion did not return a structured record for placeholder fallback.")
                return issues
            if str(placeholder_record.ingestion_status) != "placeholder_pdf_extraction":
                issues.append("Broken PDF ingestion did not preserve placeholder extraction behavior.")
            placeholder_chunks = load_document_chunks(placeholder_record.document_id)
            if not placeholder_chunks or "PDF placeholder extraction only." not in placeholder_chunks[0].content:
                issues.append("Broken PDF ingestion did not preserve the placeholder chunk content when extraction failed.")

            demo_answer = answer_course_question("What does the DEMO-101 syllabus say about attendance?")
            demo_payload = demo_answer.get("answer")
            if not isinstance(demo_payload, dict):
                issues.append("Course Q&A did not return a structured answer payload for the demo fallback query.")
                return issues
            demo_evidence = demo_payload.get("evidence")
            if not isinstance(demo_evidence, list) or not demo_evidence:
                issues.append("Course Q&A did not fall back to seed/example material when no uploaded documents existed.")
            elif any(str(item.get("source_kind") or "") != "seed_example" for item in demo_evidence if isinstance(item, dict)):
                issues.append("Course Q&A fallback did not clearly stay within seed/example material when no uploads existed.")

            list_response = client.get("/api/student-documents?limit=5")
            if list_response.status_code != 200:
                issues.append(
                    f"BattleBuddy student document listing endpoint returned HTTP {list_response.status_code}: {_validation_detail(list_response)}"
                )
                return issues
            list_payload = list_response.json()
            documents = list_payload.get("documents")
            if not isinstance(documents, list) or not documents:
                issues.append("BattleBuddy student document listing endpoint did not return the ingested file.")

            docx_upload_response = client.post(
                "/api/student-documents/upload",
                data={
                    "course_tag": "NET-301",
                    "document_category": "assignment",
                },
                files={
                    "file": (
                        "net301_assignment.docx",
                        _build_sample_docx_bytes(
                            [
                                "NET 301 Assignment Overview",
                                "Submit the packet tracer lab by Friday before 5 PM.",
                                "Include your topology diagram and routing notes.",
                            ]
                        ),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )
            if docx_upload_response.status_code != 200:
                issues.append(
                    f"BattleBuddy student document upload endpoint returned HTTP {docx_upload_response.status_code} for DOCX input: {_validation_detail(docx_upload_response)}"
                )
                return issues

            docx_payload = docx_upload_response.json()
            docx_record = docx_payload.get("record")
            if not isinstance(docx_record, dict):
                issues.append("BattleBuddy student document upload endpoint did not return a structured DOCX document record.")
                return issues
            if str(docx_record.get("filename") or "") != "net301_assignment.docx":
                issues.append("BattleBuddy DOCX upload did not preserve the original uploaded filename.")
            if str(docx_record.get("file_type") or "") != "docx":
                issues.append("BattleBuddy DOCX upload did not preserve the DOCX file type.")
            if str(docx_record.get("source_kind") or "") != "user_upload":
                issues.append("BattleBuddy DOCX upload did not preserve the user_upload source kind.")
            if not str(docx_record.get("ingestion_status") or "").startswith("ready:"):
                issues.append("BattleBuddy DOCX upload did not report a ready DOCX extraction status.")

            docx_chunks = load_document_chunks(str(docx_record.get("document_id") or ""))
            if not docx_chunks:
                issues.append("BattleBuddy DOCX upload did not generate chunks.")
                return issues
            if not any("packet tracer lab" in chunk.content.lower() for chunk in docx_chunks):
                issues.append("BattleBuddy DOCX upload did not extract real paragraph text.")
            if not any((chunk.block_index or 0) >= 2 for chunk in docx_chunks):
                issues.append("BattleBuddy DOCX upload did not preserve paragraph/block indexes in chunk metadata.")

            docx_results = search_course_documents(
                "When is the NET 301 packet tracer lab due?",
                scope="chunks",
                limit=5,
            )
            if not docx_results:
                issues.append("Course document search did not return any ranked results for the uploaded DOCX query.")
                return issues
            top_docx_result = docx_results[0]
            if str(top_docx_result.get("filename") or "") != "net301_assignment.docx":
                issues.append("Uploaded DOCX assignment was not ranked first for its exact course query.")
            if str(top_docx_result.get("course_tag") or "") != "NET-301":
                issues.append("DOCX exact course tag match did not outrank unrelated course material.")
            if int(top_docx_result.get("block_index") or 0) < 2:
                issues.append("DOCX search results did not preserve the expected paragraph/block index.")

            docx_answer = answer_course_question("When is the NET 301 packet tracer lab due?")
            docx_answer_payload = docx_answer.get("answer")
            if not isinstance(docx_answer_payload, dict):
                issues.append("Course Q&A did not return a structured answer payload for the uploaded DOCX query.")
                return issues
            docx_evidence = docx_answer_payload.get("evidence")
            if not isinstance(docx_evidence, list) or not docx_evidence:
                issues.append("Course Q&A did not attach evidence for the uploaded DOCX query.")
                return issues
            first_docx_evidence = docx_evidence[0]
            if not isinstance(first_docx_evidence, dict) or str(first_docx_evidence.get("filename") or "") != "net301_assignment.docx":
                issues.append("Course Q&A did not prioritize the uploaded DOCX evidence.")
            if int(first_docx_evidence.get("block_index") or 0) < 2:
                issues.append("Course Q&A did not preserve the DOCX paragraph/block index in attached evidence.")
            if "paragraph" not in str(docx_answer_payload.get("answer_text") or "").lower():
                issues.append("Course Q&A answer text did not cite the extracted DOCX paragraph/block context.")

            broken_docx_record = store_uploaded_course_document(
                "broken_net301_assignment.docx",
                b"not-a-docx-archive",
                course_tag="BROKEN-201",
                document_category="assignment",
            ).get("record")
            if broken_docx_record is None:
                issues.append("Broken DOCX ingestion did not return a structured record for placeholder fallback.")
                return issues
            if str(broken_docx_record.ingestion_status) != "placeholder_docx_extraction":
                issues.append("Broken DOCX ingestion did not preserve placeholder extraction behavior.")
            broken_docx_chunks = load_document_chunks(broken_docx_record.document_id)
            if not broken_docx_chunks or "DOCX placeholder extraction only." not in broken_docx_chunks[0].content:
                issues.append("Broken DOCX ingestion did not preserve the placeholder chunk content when extraction failed.")

            grounded_chat_response = client.post(
                "/api/chat",
                json={
                    "message": "What does the ITSC 2181 syllabus say about late work?",
                    "mode": "student_ops",
                    "web_enabled": True,
                },
            )
            if grounded_chat_response.status_code != 200:
                issues.append(
                    f"BattleBuddy student grounded chat path returned HTTP {grounded_chat_response.status_code}: {_validation_detail(grounded_chat_response)}"
                )
                return issues
            grounded_payload = grounded_chat_response.json()
            if str(grounded_payload.get("source_label") or "") != "Source: Local Course Material":
                issues.append("BattleBuddy student grounded chat response did not identify the local course material source label.")
            reply_text = str(grounded_payload.get("reply") or "")
            if "Grounded sources:" not in reply_text or "page 2" not in reply_text.lower() or "chunk" not in reply_text.lower():
                issues.append("BattleBuddy student grounded chat response did not cite PDF filename, page, and chunk information in the answer text.")
            source_items = grounded_payload.get("source_items")
            if not isinstance(source_items, list) or not source_items:
                issues.append("BattleBuddy student grounded chat response did not attach structured evidence items.")
            elif str(source_items[0].get("title") or "") != "itsc2181_syllabus.pdf":
                issues.append("BattleBuddy grounded chat did not cite the uploaded PDF syllabus filename first.")
            elif str(source_items[0].get("source_kind") or "") != "user_upload":
                issues.append("BattleBuddy grounded chat did not preserve the user_upload source kind in its evidence items.")
            elif int(source_items[0].get("page_number") or 0) != 2:
                issues.append("BattleBuddy grounded chat did not preserve the PDF page number in its evidence items.")

            docx_grounded_response = client.post(
                "/api/chat",
                json={
                    "message": "When is the NET 301 packet tracer lab due?",
                    "mode": "student_ops",
                    "web_enabled": True,
                },
            )
            if docx_grounded_response.status_code != 200:
                issues.append(
                    f"BattleBuddy DOCX grounded chat path returned HTTP {docx_grounded_response.status_code}: {_validation_detail(docx_grounded_response)}"
                )
                return issues
            docx_grounded_payload = docx_grounded_response.json()
            docx_reply = str(docx_grounded_payload.get("reply") or "")
            if "net301_assignment.docx" not in docx_reply or "paragraph" not in docx_reply.lower():
                issues.append("BattleBuddy grounded chat response did not cite the uploaded DOCX filename and paragraph context.")
            docx_source_items = docx_grounded_payload.get("source_items")
            if not isinstance(docx_source_items, list) or not docx_source_items:
                issues.append("BattleBuddy DOCX grounded chat response did not attach structured evidence items.")
            elif str(docx_source_items[0].get("title") or "") != "net301_assignment.docx":
                issues.append("BattleBuddy grounded chat did not cite the uploaded DOCX filename first.")
            elif int(docx_source_items[0].get("block_index") or 0) < 2:
                issues.append("BattleBuddy grounded chat did not preserve the DOCX paragraph/block index in its evidence items.")

            insufficient_response = client.post(
                "/api/chat",
                json={
                    "message": "What do my uploaded notes say about interstellar llama harmonics and quaternion pastry theorems?",
                    "mode": "student_ops",
                    "web_enabled": True,
                },
            )
            if insufficient_response.status_code != 200:
                issues.append(
                    f"BattleBuddy insufficient-evidence student chat path returned HTTP {insufficient_response.status_code}: {_validation_detail(insufficient_response)}"
                )
                return issues
            insufficient_payload = insufficient_response.json()
            insufficient_reply = str(insufficient_payload.get("reply") or "").lower()
            source_status = str(insufficient_payload.get("source_status") or "").strip().lower()
            source_items = insufficient_payload.get("source_items")
            if not insufficient_reply:
                issues.append("BattleBuddy student chat path did not report insufficient evidence clearly when no grounded support existed.")
            elif source_status not in {"verified_source", "missing_verified_source", "insufficient_evidence"}:
                issues.append("BattleBuddy student chat path returned an unexpected source status for the unsupported grounded query.")
            elif not isinstance(source_items, list):
                issues.append("BattleBuddy student chat path did not return a structured source_items list for the unsupported grounded query.")

            combined_response = client.post(
                "/api/chat",
                json={
                    "message": "When is my next class and what does the ITSC 2181 syllabus say about attendance?",
                    "mode": "student_ops",
                    "web_enabled": False,
                },
            )
            if combined_response.status_code != 200:
                issues.append(
                    f"BattleBuddy combined student document and calendar chat path returned HTTP {combined_response.status_code}: {_validation_detail(combined_response)}"
                )
                return issues
            combined_payload = combined_response.json()
            if str(combined_payload.get("source_label") or "") != "Source: Local Course Material + Sitrep / Dashboard":
                issues.append("BattleBuddy combined student document and calendar answer did not preserve the read-only mixed-source label.")
            combined_reply = str(combined_payload.get("reply") or "")
            if "Read-only calendar context:" not in combined_reply:
                issues.append("BattleBuddy combined student answer did not expose calendar context as read-only.")
            if combined_payload.get("proposed_actions"):
                issues.append("BattleBuddy combined student answer should not add autonomous actions while presenting read-only calendar context.")
    finally:
        if previous_docs_root is None:
            os.environ.pop("TITAN_COURSE_DOCUMENTS_DIR", None)
        else:
            os.environ["TITAN_COURSE_DOCUMENTS_DIR"] = previous_docs_root

    return issues


def main() -> int:
    issues: list[str] = []
    details = python_runtime_summary()
    details["student_mode_config_path"] = str(STUDENT_MODE_CONFIG_PATH)
    details["courses_root"] = str(COURSES_ROOT)
    details["expected_supported_extensions"] = EXPECTED_EXTENSIONS
    details["battlebuddy_student_document_routes"] = _route_table_snapshot()

    issues.extend(_validate_student_mode_config())
    issues.extend(_validate_mode_aliases())
    issues.extend(_validate_policy_behavior())
    issues.extend(_validate_prompt_behavior())
    issues.extend(_validate_course_manifests())
    issues.extend(_validate_student_workspace_layout())
    issues.extend(_validate_battlebuddy_route_registration())
    issues.extend(_validate_battlebuddy_student_documents())

    return print_validation_report("Titan Student Mode Validation", issues, details)


if __name__ == "__main__":
    raise SystemExit(main())
