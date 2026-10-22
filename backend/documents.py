"""Medical documents, with sources.

A family uploads a PDF. The model reads it through a FORCED tool call with a strict schema, so its output is
structured, not free text. Every finding must quote the document's own words, and this code checks each quote
against the page text. A finding whose quote is not on the page cannot be approved. The family approves each
finding, and only an approved finding becomes something the companion may say, always with its source.
The companion never advises on it: it reports what the document says and points to the doctor.
"""
import asyncio
import base64
import hashlib
import io
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Literal

import anthropic
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import db
import episodic_memory
import family
import llm

log = logging.getLogger("documents")
router = APIRouter(prefix="/family")

EXTRACT_MODELS = ("claude-sonnet-5-5", llm.CLAUDE_MODEL)  # accuracy matters here and nothing waits on it
MAX_BYTES = 3 * 1024 * 1024
MAX_PAGES = 30
MIN_QUOTE = 12  # a shorter "quote" proves nothing
# Only these ever reach the companion. A diagnosis or a test score can be approved as a record for the family,
# but the companion never says it to the person.
COMPANION_KINDS = {"medication", "appointment", "instruction", "contact"}

TYPE_LABEL = {
    "clinic_letter": "clinic letter", "prescription": "prescription", "lab_result": "test result",
    "discharge_summary": "discharge summary", "appointment": "appointment letter", "other": "document",
}

SYSTEM = """You read a medical document for the family of a person with memory loss, and record what it says.
Rules:
- Record only what is written. Never infer, never add medical knowledge, never complete a dose or a schedule the document does not state.
- Every finding must quote the exact words from the page, copied character for character, and give that page number.
- One finding per medicine, appointment, instruction, test result or stated diagnosis. Keep each summary to one plain sentence.
- For a medicine, fill in name, dose, frequency, timing and duration only if the document states them. Use null for anything it does not state.
- Record a stated diagnosis as kind "diagnosis_stated", using the document's own words. Do not comment on it.
- If the page text is not a medical document or is unreadable, return no findings."""

_NULLABLE_STR = {"type": ["string", "null"]}
TOOL = {
    "name": "record_findings",
    "description": "Record what the document says, and nothing else. Every finding needs the exact words that support it.",
    "input_schema": {
        "type": "object",
        "properties": {
            "document": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(TYPE_LABEL)},
                    "date": {"type": ["string", "null"], "description": "Date of the document as YYYY-MM-DD, or null"},
                    "author": _NULLABLE_STR,
                    "patient_name": {"type": ["string", "null"], "description": "Who the document says it is about"},
                },
                "required": ["type", "date", "author", "patient_name"],
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["medication", "appointment", "instruction", "test_result", "diagnosis_stated", "contact", "other"]},
                        "summary": {"type": "string", "description": "One plain sentence stating what the document says"},
                        "page": {"type": "integer", "description": "1-based page number"},
                        "quote": {"type": "string", "description": "The exact words from that page that support this finding"},
                        "medication": {
                            "type": ["object", "null"],
                            "properties": {"name": _NULLABLE_STR, "dose": _NULLABLE_STR, "frequency": _NULLABLE_STR,
                                           "timing": _NULLABLE_STR, "duration": _NULLABLE_STR,
                                           "change": {"type": ["string", "null"], "enum": ["new", "increase", "decrease", "stop", "continue", None]}},
                        },
                        "appointment": {
                            "type": ["object", "null"],
                            "properties": {"when": _NULLABLE_STR, "where": _NULLABLE_STR, "with": _NULLABLE_STR},
                        },
                    },
                    "required": ["kind", "summary", "page", "quote"],
                },
            },
        },
        "required": ["document", "findings"],
    },
}


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def locate(quote: str, pages: list[str], claimed: int) -> int | None:
    """The page the quote really appears on, word for word (ignoring spacing and case), or None."""
    q = _norm(quote)
    if len(q) < MIN_QUOTE:
        return None
    order = ([claimed - 1] if 1 <= claimed <= len(pages) else []) + [i for i in range(len(pages)) if i != claimed - 1]
    for i in order:
        if q in _norm(pages[i]):
            return i + 1
    return None


def _read_pdf(raw: bytes) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    return [(p.extract_text() or "").strip() for p in reader.pages][:MAX_PAGES]


async def _call_tool(pages: list[str]) -> dict:
    user = "\n\n".join(f"--- PAGE {i + 1} ---\n{t}" for i, t in enumerate(pages))
    last = None
    for model in EXTRACT_MODELS:
        try:
            resp = await llm.claude.messages.create(
                model=model, max_tokens=4000, system=SYSTEM, messages=[{"role": "user", "content": user}],
                tools=[TOOL], tool_choice={"type": "tool", "name": "record_findings"},
                thinking={"type": "disabled"},  # a forced tool call cannot be combined with extended thinking
            )
            block = next(b for b in resp.content if b.type == "tool_use")
            return block.input
        except (anthropic.APIError, StopIteration) as e:
            last = e
            log.warning("extraction with %s failed: %s", model, type(e).__name__)
    raise RuntimeError(f"extraction failed: {type(last).__name__}")


def _label(doc_type: str | None, author: str | None, doc_date: date | None) -> str:
    out = f"the {TYPE_LABEL.get(doc_type or 'other', 'document')}"
    if author:
        out += f" from {author}"
    if doc_date:
        out += f" dated {doc_date.day} {doc_date.strftime('%B %Y')}"
    return out


async def _extract(did: int) -> None:
    """Runs in the background: reads the pages, calls the tool, checks every quote, stores the findings."""
    try:
        async with db.pool.connection() as conn:
            pid, pages = await (await conn.execute("SELECT patient_id, pages FROM documents WHERE id = %s", (did,))).fetchone()
        data = await _call_tool(pages)
        meta = data.get("document") or {}
        try:
            when = date.fromisoformat(meta.get("date")) if meta.get("date") else None
        except ValueError:
            when = None
        rows = []
        for f in data.get("findings") or []:
            quote = (f.get("quote") or "").strip()
            page = locate(quote, pages, int(f.get("page") or 1))
            detail = {k: v for k in ("medication", "appointment") if isinstance(f.get(k), dict)
                      for v in [{a: b for a, b in f[k].items() if b}] if v} or None
            rows.append((pid, f.get("kind", "other"), (f.get("summary") or "").strip()[:400],
                         json.dumps(detail) if detail else None, page or int(f.get("page") or 1), quote[:600], page is not None))
        async with db.pool.connection() as conn:
            for r in rows:
                await conn.execute(
                    "INSERT INTO document_facts (document_id, patient_id, kind, summary, detail, page, quote, verified) "
                    "VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)", (did, *r))
            await conn.execute(
                "UPDATE documents SET status = 'ready', doc_type = %s, doc_date = %s, author = %s, named_patient = %s WHERE id = %s",
                (meta.get("type"), when, meta.get("author"), meta.get("patient_name"), did))
    except Exception as e:
        log.exception("document %s failed", did)
        async with db.pool.connection() as conn:
            await conn.execute("UPDATE documents SET status = 'failed', error = %s WHERE id = %s", (str(e)[:200], did))


_tasks: set[asyncio.Task] = set()


class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_b64: str = Field(min_length=20)


@router.post("/{pid}/documents")
async def upload(pid: int, body: UploadIn, request: Request):
    try:
        raw = base64.b64decode(body.content_b64, validate=True)
    except Exception:
        return JSONResponse({"detail": "the file could not be read"}, status_code=422)
    if len(raw) > MAX_BYTES:
        return JSONResponse({"detail": "the file is larger than 3 MB"}, status_code=413)
    if not raw.startswith(b"%PDF"):
        return JSONResponse({"detail": "only PDF files are supported"}, status_code=422)
    try:
        pages = await asyncio.to_thread(_read_pdf, raw)
    except Exception:
        return JSONResponse({"detail": "this PDF cannot be read (it may be protected)"}, status_code=422)
    if sum(len(p) for p in pages) < 80:
        return JSONResponse({"detail": "no text found. Scanned documents are not supported yet"}, status_code=422)
    sha = hashlib.sha256(raw).hexdigest()
    actor = family.actor_of(request)
    async with db.pool.connection() as conn:
        if not await (await conn.execute("SELECT 1 FROM patients WHERE id = %s", (pid,))).fetchone():
            return JSONResponse({"detail": "not found"}, status_code=404)
        dup = await (await conn.execute("SELECT id FROM documents WHERE patient_id = %s AND sha256 = %s", (pid, sha))).fetchone()
        if dup:
            return {"id": dup[0], "existing": True}
        row = await (await conn.execute(
            "INSERT INTO documents (patient_id, filename, sha256, pages, uploaded_by) VALUES (%s, %s, %s, %s::jsonb, %s) RETURNING id",
            (pid, body.filename.strip()[:200], sha, json.dumps(pages), actor))).fetchone()
    await family.audit(pid, actor, "document_uploaded", body.filename.strip()[:100])
    t = asyncio.create_task(_extract(row[0]))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return {"id": row[0], "existing": False}


@router.get("/{pid}/documents")
async def list_documents(pid: int):
    async with db.pool.connection() as conn:
        rows = await (await conn.execute(
            """SELECT d.id, d.filename, d.status, d.error, d.doc_type, d.doc_date, d.author, d.uploaded_by, d.uploaded_at,
                      count(f.id) FILTER (WHERE f.status = 'pending'), count(f.id) FILTER (WHERE f.status = 'approved'),
                      count(f.id) FILTER (WHERE f.status = 'rejected')
               FROM documents d LEFT JOIN document_facts f ON f.document_id = d.id
               WHERE d.patient_id = %s GROUP BY d.id ORDER BY d.uploaded_at DESC""", (pid,))).fetchall()
    return {"documents": [dict(
        id=i, filename=fn, status=st, error=er, type=ty, date=dd.isoformat() if dd else None, author=au, uploaded_by=ub,
        uploaded_at=ua.isoformat(), pending=p, approved=a, rejected=r) for i, fn, st, er, ty, dd, au, ub, ua, p, a, r in rows]}


def _same_person(patient: str, named: str | None) -> bool:
    if not named:
        return True  # the document does not say, so there is nothing to contradict
    tokens = [t for t in re.split(r"\W+", _norm(patient)) if len(t) > 1]
    return any(t in _norm(named) for t in tokens)


@router.get("/{pid}/documents/medicines")
async def approved_medicines(pid: int):
    """Medicines the family has approved from documents, so the setup form can offer them. Declared before the
    /{did} route, or "medicines" would be read as a document number."""
    async with db.pool.connection() as conn:
        rows = await (await conn.execute(
            """SELECT f.detail, d.doc_type, d.author, d.doc_date FROM document_facts f JOIN documents d ON d.id = f.document_id
               WHERE f.patient_id = %s AND f.status = 'approved' AND f.kind = 'medication' ORDER BY d.doc_date DESC NULLS LAST, f.id""", (pid,))).fetchall()
    seen, out = set(), []
    for detail, dtype, author, ddate in rows:
        med = (detail or {}).get("medication") or {}
        name = (med.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"name": name, "dose": med.get("dose"), "frequency": med.get("frequency"), "timing": med.get("timing"),
                    "source": _label(dtype, author, ddate)})
    return {"medicines": out}


@router.get("/{pid}/documents/{did}")
async def get_document(pid: int, did: int):
    async with db.pool.connection() as conn:
        d = await (await conn.execute(
            """SELECT d.filename, d.status, d.error, d.doc_type, d.doc_date, d.author, d.named_patient, d.uploaded_by, d.uploaded_at, p.name
               FROM documents d JOIN patients p ON p.id = d.patient_id WHERE d.id = %s AND d.patient_id = %s""", (did, pid))).fetchone()
        if not d:
            return JSONResponse({"detail": "not found"}, status_code=404)
        facts = await (await conn.execute(
            """SELECT id, kind, summary, detail, page, quote, verified, status, reviewed_by, reviewed_at
               FROM document_facts WHERE document_id = %s ORDER BY page, id""", (did,))).fetchall()
        others = await (await conn.execute(
            """SELECT f.detail, d.doc_type, d.author, d.doc_date FROM document_facts f JOIN documents d ON d.id = f.document_id
               WHERE f.patient_id = %s AND f.document_id <> %s AND f.status = 'approved' AND f.kind = 'medication'""", (pid, did))).fetchall()
    fn, st, er, ty, dd, au, named, ub, ua, pname = d
    out = []
    for fid, kind, summary, detail, page, quote, verified, status, rb, ra in facts:
        conflict = None
        med = (detail or {}).get("medication") if kind == "medication" else None
        if med and med.get("name"):
            same = [(o, t, a, w) for o, t, a, w in others if ((o or {}).get("medication") or {}).get("name", "").lower() == med["name"].lower()]
            if same and not any(_norm(((o or {}).get("medication") or {}).get("dose") or "") == _norm(med.get("dose") or "") for o, *_ in same):
                o, t, a, w = same[0]
                conflict = f"{_label(t, a, w).capitalize()} lists {med['name']} at a different dose."
        out.append(dict(id=fid, kind=kind, summary=summary, detail=detail, page=page, quote=quote, verified=verified,
                        companion_can_say=kind in COMPANION_KINDS, status=status, reviewed_by=rb, reviewed_at=ra.isoformat() if ra else None, conflict=conflict))
    return {
        "id": did, "filename": fn, "status": st, "error": er, "type": ty, "date": dd.isoformat() if dd else None, "author": au,
        "named_patient": named, "name_mismatch": not _same_person(pname, named), "patient": pname,
        "uploaded_by": ub, "uploaded_at": ua.isoformat(), "facts": out,
    }


class ReviewIn(BaseModel):
    action: Literal["approve", "reject"]


@router.post("/{pid}/documents/{did}/facts/{fid}")
async def review_fact(pid: int, did: int, fid: int, body: ReviewIn, request: Request):
    actor = family.actor_of(request)
    async with db.pool.connection() as conn:
        row = await (await conn.execute(
            """SELECT f.kind, f.summary, f.page, f.quote, f.verified, f.status, f.memory_id, d.doc_type, d.author, d.doc_date
               FROM document_facts f JOIN documents d ON d.id = f.document_id
               WHERE f.id = %s AND f.document_id = %s AND f.patient_id = %s""", (fid, did, pid))).fetchone()
    if not row:
        return JSONResponse({"detail": "not found"}, status_code=404)
    kind, summary, page, quote, verified, status, memory_id, dtype, author, ddate = row

    if body.action == "approve":
        if not verified:
            return JSONResponse({"detail": "the quoted words were not found on that page, so this cannot be approved"}, status_code=409)
        if status == "approved":
            return {"status": "approved", "companion_can_say": memory_id is not None}
        speakable = kind in COMPANION_KINDS
        content = f"According to {_label(dtype, author, ddate)}, page {page}: {summary} The document says: \"{quote}\""
        mid = await episodic_memory.save_memory(pid, content, "medical", None, "document") if speakable else None
        async with db.pool.connection() as conn:
            await conn.execute(
                "UPDATE document_facts SET status = 'approved', reviewed_by = %s, reviewed_at = now(), memory_id = %s WHERE id = %s",
                (actor, mid, fid))
        await family.audit(pid, actor, "document_fact_approved", f"{kind}, page {page}" + ("" if speakable else ", family record only"))
        return {"status": "approved", "companion_can_say": speakable}

    async with db.pool.connection() as conn:  # reject, or withdraw an earlier approval
        if memory_id:
            await conn.execute("DELETE FROM memories WHERE id = %s AND patient_id = %s", (memory_id, pid))
        await conn.execute(
            "UPDATE document_facts SET status = 'rejected', reviewed_by = %s, reviewed_at = now(), memory_id = NULL WHERE id = %s", (actor, fid))
    await family.audit(pid, actor, "document_fact_rejected", f"{kind}, page {page}")
    return {"status": "rejected"}


@router.post("/{pid}/documents/{did}/delete")
async def delete_document(pid: int, did: int, request: Request):
    """Removes the document, its findings, and everything the companion learned from it."""
    async with db.pool.connection() as conn:
        row = await (await conn.execute("SELECT filename FROM documents WHERE id = %s AND patient_id = %s", (did, pid))).fetchone()
        if not row:
            return JSONResponse({"detail": "not found"}, status_code=404)
        await conn.execute(
            "DELETE FROM memories WHERE patient_id = %s AND id IN (SELECT memory_id FROM document_facts WHERE document_id = %s AND memory_id IS NOT NULL)",
            (pid, did))
        await conn.execute("DELETE FROM documents WHERE id = %s", (did,))  # the findings go with it
    await family.audit(pid, family.actor_of(request), "document_deleted", row[0][:100])
    return {"deleted": True}
