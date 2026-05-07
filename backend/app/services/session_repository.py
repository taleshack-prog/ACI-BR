"""
Repository de Sessões Clínicas — MongoDB.

Todas as operações de staging (AWAITING_REVIEW → SYNCED) passam por aqui.
TTL index de 30 dias configurado via ensure_indexes().
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.session import ClinicalSession, AuditEntry
from app.config import settings
import logging

logger = logging.getLogger(__name__)

COLLECTION = "clinical_sessions"


async def ensure_indexes(db: AsyncIOMotorDatabase):
    """Cria indexes necessários incluindo TTL de 30 dias."""
    col = db[COLLECTION]
    await col.create_index("session_id", unique=True)
    await col.create_index("doctor_id")
    await col.create_index("patient_id")
    await col.create_index("review_status")
    await col.create_index(
        "expires_at",
        expireAfterSeconds=0,  # TTL — MongoDB deleta quando expires_at < now()
    )
    logger.info("MongoDB indexes OK")


def _ttl() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.SESSION_TTL_DAYS)


async def create_session(db: AsyncIOMotorDatabase, session: ClinicalSession) -> str:
    session.expires_at = _ttl()
    session.audit_trail.append(AuditEntry(action="SESSION_CREATED"))
    doc = session.model_dump(by_alias=True)
    doc["_id"] = doc.get("_id") or str(ObjectId())
    result = await db[COLLECTION].insert_one(doc)
    logger.info(f"Sessão criada: {session.session_id}")
    return session.session_id


async def get_session(db: AsyncIOMotorDatabase, session_id: str) -> Optional[dict]:
    return await db[COLLECTION].find_one({"session_id": session_id}, {"_id": 0})


async def update_session(db: AsyncIOMotorDatabase, session_id: str, updates: dict) -> bool:
    updates["updated_at"] = datetime.now(timezone.utc)
    result = await db[COLLECTION].update_one(
        {"session_id": session_id},
        {"$set": updates},
    )
    return result.modified_count > 0


async def append_audit(db: AsyncIOMotorDatabase, session_id: str, entry: AuditEntry):
    await db[COLLECTION].update_one(
        {"session_id": session_id},
        {
            "$push": {"audit_trail": entry.model_dump()},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )


async def list_sessions_by_doctor(
    db: AsyncIOMotorDatabase,
    doctor_id: str,
    status: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    query: dict = {"doctor_id": doctor_id}
    if status:
        query["review_status"] = status
    cursor = db[COLLECTION].find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def delete_session(db: AsyncIOMotorDatabase, session_id: str) -> bool:
    result = await db[COLLECTION].delete_one({"session_id": session_id})
    return result.deleted_count > 0
