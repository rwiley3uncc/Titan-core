from __future__ import annotations

from email.parser import BytesParser
from email.policy import default
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from titan_core.event_log import emit_battlebuddy_event
from titan_core.titan_shared_imports import ensure_titan_shared_on_path

ensure_titan_shared_on_path()

from titan_shared.course_document_store import (  # noqa: E402
    list_document_records,
    store_uploaded_course_document,
)


router = APIRouter()


def _invalid_student_document_request(message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "status": "invalid_request",
            "message": message,
        },
    )


def _document_collection_payload(
    *,
    course_tag: str | None = None,
    document_category: str | None = None,
    limit: int = 12,
) -> dict[str, object]:
    collection = list_document_records(
        course_tag=course_tag,
        document_category=document_category,
    )
    documents = collection.documents[: max(1, int(limit or 1))]
    return {
        "collection_id": collection.collection_id,
        "generated_at": collection.generated_at,
        "total_documents": collection.total_documents,
        "total_chunks": collection.total_chunks,
        "course_tag": collection.course_tag,
        "document_category": collection.document_category,
        "documents": [document.to_dict() for document in documents],
        "returned_documents": len(documents),
    }


async def _parse_multipart_student_upload(request: Request) -> tuple[str, bytes, str, str]:
    content_type = str(request.headers.get("content-type") or "").strip()
    if "multipart/form-data" not in content_type.lower():
        raise _invalid_student_document_request("Student document upload requires multipart form data.")

    body = await request.body()
    if not body:
        raise _invalid_student_document_request("Student document upload body was empty.")

    message = BytesParser(policy=default).parsebytes(
        (
            f"Content-Type: {content_type}\r\n"
            "MIME-Version: 1.0\r\n\r\n"
        ).encode("utf-8")
        + body
    )

    file_name = ""
    file_content = b""
    course_tag = ""
    document_category = ""

    for part in message.iter_parts():
        field_name = str(part.get_param("name", header="content-disposition") or "").strip()
        if not field_name:
            continue
        if field_name == "file":
            file_name = Path(str(part.get_filename() or "").strip()).name
            file_content = part.get_payload(decode=True) or b""
            continue

        value = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", errors="replace").strip()
        if field_name == "course_tag":
            course_tag = value
        elif field_name == "document_category":
            document_category = value

    return file_name, file_content, course_tag, document_category


@router.post("/student-documents/upload")
async def upload_student_document(
    request: Request,
) -> dict[str, object]:
    filename, content, course_tag, document_category = await _parse_multipart_student_upload(request)
    if not filename:
        raise _invalid_student_document_request("A local class file is required.")

    if not content:
        raise _invalid_student_document_request("The selected class file was empty.")

    try:
        ingestion_result = store_uploaded_course_document(
            filename,
            content,
            course_tag=course_tag,
            document_category=document_category,
        )
    except ValueError as exc:
        raise _invalid_student_document_request(str(exc)) from exc

    record = ingestion_result["record"]
    emit_battlebuddy_event(
        subsystem="battlebuddy",
        severity="INFO",
        event_type="student_document_ingested",
        summary="Student document ingested into local course memory.",
        details=(
            f"Document: {record.filename} | Course: {record.course_tag} | "
            f"Category: {record.document_category} | Chunks: {record.chunk_count}"
        ),
        confidence=0.95,
        risk="low",
        status="completed",
    )
    return {
        "status": "ingested",
        "record": record.to_dict(),
        "chunk_count": record.chunk_count,
        "storage": ingestion_result.get("storage") or {},
    }


@router.get("/student-documents")
def list_student_documents(
    course_tag: str | None = Query(default=None),
    document_category: str | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
) -> dict[str, object]:
    return _document_collection_payload(
        course_tag=course_tag,
        document_category=document_category,
        limit=limit,
    )
