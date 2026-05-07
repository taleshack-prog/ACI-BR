"""
Session Endpoints — Human-in-the-Loop Review Flow.

  GET  /session/{session_id}          — recupera sessão
  PUT  /session/{session_id}          — aprova/rejeita sessão
  POST /session/{session_id}/corrections — submete correções de chips
  POST /session/{session_id}/sync     — dispara write-back ao PEP
  DELETE /session/{session_id}        — descarta sessão
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime, timezone

from app.models.session import EntityCorrection

router = APIRouter()


class ReviewUpdate(BaseModel):
    review_status: Literal["APPROVED", "REJECTED"]
    reviewed_by: str
    reviewed_at: Optional[datetime] = None


class CorrectionsRequest(BaseModel):
    corrections: List[EntityCorrection]


# In-memory store para protótipo — substituir por MongoDB
_sessions_store: dict = {}


@router.get("/{session_id}")
async def get_session(session_id: str):
    session = _sessions_store.get(session_id)
    if not session:
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")
    return session


@router.put("/{session_id}")
async def update_session_review(session_id: str, body: ReviewUpdate):
    """
    Médico aprova ou rejeita a nota clínica gerada pela IA.
    Transição: AWAITING_REVIEW → APPROVED | REJECTED
    """
    session = _sessions_store.get(session_id)
    if not session:
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")

    session["review_status"] = body.review_status
    session["reviewed_by"] = body.reviewed_by
    session["reviewed_at"] = (body.reviewed_at or datetime.now(timezone.utc)).isoformat()
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    session.setdefault("audit_trail", []).append({
        "action": f"REVIEW_{body.review_status}",
        "actor_id": body.reviewed_by,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    return {"message": f"Sessão {session_id} {body.review_status.lower()}.", "session": session}


@router.post("/{session_id}/corrections")
async def submit_corrections(session_id: str, body: CorrectionsRequest):
    """
    Médico edita chips de entidades clínicas na interface de revisão.
    Cada correção é registrada para active learning / fine-tuning.
    """
    session = _sessions_store.get(session_id)
    if not session:
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")

    corrections_list = session.setdefault("corrections", [])
    for c in body.corrections:
        corrections_list.append(c.model_dump())

    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    session.setdefault("audit_trail", []).append({
        "action": "CORRECTIONS_SUBMITTED",
        "details": {"count": len(body.corrections)},
        "at": datetime.now(timezone.utc).isoformat(),
    })
    return {"message": f"{len(body.corrections)} correção(ões) registrada(s).", "session_id": session_id}


@router.post("/{session_id}/sync")
async def sync_to_ehr(session_id: str):
    """
    Dispara o write-back para o PEP/EHR após aprovação médica.
    Transição: APPROVED → SYNCED | FAILED
    """
    session = _sessions_store.get(session_id)
    if not session:
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")

    if session.get("review_status") != "APPROVED":
        raise HTTPException(400, detail="Sessão deve estar APPROVED antes de sincronizar.")

    # TODO: implementar write-back real via ehr_service
    session["sync_status"] = "SYNCED"
    session["synced_at"] = datetime.now(timezone.utc).isoformat()
    session["review_status"] = "SYNCED"
    session.setdefault("audit_trail", []).append({
        "action": "SYNCED_TO_EHR",
        "at": datetime.now(timezone.utc).isoformat(),
    })
    return {"message": "Nota sincronizada com o PEP com sucesso.", "session_id": session_id}


@router.delete("/{session_id}", status_code=204)
async def discard_session(session_id: str):
    """
    Descarta a sessão (médico optou por não salvar).
    Transição: AWAITING_REVIEW → DISCARDED
    """
    session = _sessions_store.get(session_id)
    if not session:
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")
    session["review_status"] = "DISCARDED"
    session["sync_status"] = "DISCARDED"
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    return
