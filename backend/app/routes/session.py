"""
Session Endpoints — MongoDB persistence + EHR write-back.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime, timezone
import uuid

from app.models.session import (
    ClinicalSession, EntityCorrection, AuditEntry,
)
from app.services.auth_service import require_doctor, TokenPayload
from app.services.ehr_service import write_back_to_ehr

router = APIRouter()

# In-memory fallback (usado quando MongoDB não está disponível)
_sessions: dict = {}


async def _get_db():
    try:
        from app.database import get_mongo_db
        return await get_mongo_db()
    except Exception:
        return None


async def _load_session(session_id: str) -> Optional[dict]:
    db = await _get_db()
    if db is not None:
        from app.services.session_repository import get_session
        return await get_session(db, session_id)
    return _sessions.get(session_id)


async def _save_session(session_id: str, data: dict):
    db = await _get_db()
    if db is not None:
        from app.services.session_repository import update_session
        await update_session(db, session_id, data)
    else:
        if session_id in _sessions:
            _sessions[session_id].update(data)


class ReviewUpdate(BaseModel):
    review_status: Literal["APPROVED", "REJECTED"]
    reviewed_at: Optional[datetime] = None


class CorrectionsRequest(BaseModel):
    corrections: List[EntityCorrection]


class CreateSessionRequest(BaseModel):
    patient_id: str
    specialty: str = "general"
    soap: Optional[dict] = None
    entities: Optional[list] = None
    fhir_bundle: Optional[dict] = None


@router.post("", status_code=201)
async def create_session(
    body: CreateSessionRequest,
    current_user: TokenPayload = Depends(require_doctor),
):
    """Cria nova sessão clínica com dados do pipeline."""
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    session = {
        "session_id": session_id,
        "patient_id": body.patient_id,
        "doctor_id": current_user.sub,
        "specialty": body.specialty,
        "soap": body.soap,
        "entities": body.entities or [],
        "fhir_resources": body.fhir_bundle,
        "review_status": "AWAITING_REVIEW",
        "sync_status": "PENDING",
        "corrections": [],
        "created_at": now,
        "updated_at": now,
        "audit_trail": [{"action": "SESSION_CREATED", "actor_id": current_user.sub, "at": now}],
    }

    db = await _get_db()
    if db is not None:
        try:
            from app.services.session_repository import create_session as db_create
            from app.models.session import ClinicalSession, SOAPNote
            cs = ClinicalSession(
                session_id=session_id,
                patient_id=body.patient_id,
                doctor_id=current_user.sub,
                specialty=body.specialty,
            )
            await db_create(db, cs)
        except Exception as e:
            pass  # fallback to memory
    _sessions[session_id] = session

    return {"session_id": session_id, "status": "AWAITING_REVIEW"}


@router.get("")
async def list_sessions(
    status: Optional[str] = None,
    current_user: TokenPayload = Depends(require_doctor),
):
    """Lista sessões do médico autenticado."""
    db = await _get_db()
    if db is not None:
        try:
            from app.services.session_repository import list_sessions_by_doctor
            sessions = await list_sessions_by_doctor(db, current_user.sub, status)
            return {"sessions": sessions, "total": len(sessions)}
        except Exception:
            pass

    sessions = [s for s in _sessions.values() if s.get("doctor_id") == current_user.sub]
    if status:
        sessions = [s for s in sessions if s.get("review_status") == status]
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    current_user: TokenPayload = Depends(require_doctor),
):
    session = await _load_session(session_id) or _sessions.get(session_id)
    if not session:
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")
    if session.get("doctor_id") != current_user.sub and current_user.role != "ADMIN":
        raise HTTPException(403, detail="Sem permissão.")
    return session


@router.put("/{session_id}")
async def update_review(
    session_id: str,
    body: ReviewUpdate,
    current_user: TokenPayload = Depends(require_doctor),
):
    """Médico aprova ou rejeita a nota gerada pela IA."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")

    now = datetime.now(timezone.utc).isoformat()
    session["review_status"] = body.review_status
    session["reviewed_by"] = current_user.sub
    session["reviewed_at"] = (body.reviewed_at or datetime.now(timezone.utc)).isoformat()
    session["updated_at"] = now
    session.setdefault("audit_trail", []).append({
        "action": f"REVIEW_{body.review_status}",
        "actor_id": current_user.sub,
        "at": now,
    })
    await _save_session(session_id, session)
    return {"message": f"Sessão {body.review_status.lower()}.", "session_id": session_id}


@router.post("/{session_id}/corrections")
async def submit_corrections(
    session_id: str,
    body: CorrectionsRequest,
    current_user: TokenPayload = Depends(require_doctor),
):
    """Registra correções de chips para active learning."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")

    for c in body.corrections:
        session.setdefault("corrections", []).append(c.model_dump())

    now = datetime.now(timezone.utc).isoformat()
    session["updated_at"] = now
    session.setdefault("audit_trail", []).append({
        "action": "CORRECTIONS_SUBMITTED",
        "actor_id": current_user.sub,
        "details": {"count": len(body.corrections)},
        "at": now,
    })
    await _save_session(session_id, session)
    return {"message": f"{len(body.corrections)} correção(ões) registrada(s)."}


@router.post("/{session_id}/sync")
async def sync_to_ehr(
    session_id: str,
    ehr_target: str = "simulator",
    current_user: TokenPayload = Depends(require_doctor),
):
    """
    Write-back para o PEP com retry exponencial.
    ehr_target: "simulator" | "tasy" | "mv"
    """
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")
    if session.get("review_status") != "APPROVED":
        raise HTTPException(400, detail="Sessão deve estar APPROVED antes de sincronizar.")

    fhir_bundle = session.get("fhir_resources") or {"resourceType": "Bundle", "entry": []}

    result = await write_back_to_ehr(
        fhir_bundle=fhir_bundle,
        session_id=session_id,
        ehr_target=ehr_target,
    )

    now = datetime.now(timezone.utc).isoformat()
    if result["success"]:
        session["sync_status"] = "SYNCED"
        session["review_status"] = "SYNCED"
        session["synced_at"] = result["synced_at"]
        session["fhir_ids"] = result["fhir_ids"]
        session.setdefault("audit_trail", []).append({
            "action": "SYNCED_TO_EHR",
            "actor_id": current_user.sub,
            "details": {"ehr": result["ehr"], "attempts": result["attempts"]},
            "at": now,
        })
        await _save_session(session_id, session)
        return {
            "message": f"Nota sincronizada com {result['ehr']} em {result['attempts']} tentativa(s).",
            "fhir_ids": result["fhir_ids"],
            "session_id": session_id,
        }
    else:
        session["sync_status"] = "FAILED"
        session.setdefault("sync_errors", []).append(result["error"])
        await _save_session(session_id, session)
        raise HTTPException(502, detail=f"Falha no write-back: {result['error']}")


@router.delete("/{session_id}", status_code=204)
async def discard_session(
    session_id: str,
    current_user: TokenPayload = Depends(require_doctor),
):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")
    session["review_status"] = "DISCARDED"
    session["sync_status"] = "DISCARDED"
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    await _save_session(session_id, session)
