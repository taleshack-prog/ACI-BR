"""
Schema da Sessão Clínica — MongoDB (Staging Area).

Armazena o estado temporário AWAITING_REVIEW antes do write-back no PEP.
TTL: 30 dias (index MongoDB em expiresAt).
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime, timezone
import uuid


# ─── Sub-modelos ──────────────────────────────────────────────────────────────

class AudioMetadata(BaseModel):
    duration: float  # segundos
    sample_rate: int = 16000
    channels: int = 1
    format: str = "pcm/wav"


class DiarizationSegment(BaseModel):
    start: float
    end: float
    text: str


class SpeakerInfo(BaseModel):
    speaker_id: str
    role: Literal["doctor", "patient", "unknown"]
    segments: List[DiarizationSegment] = []


class DiarizationOutput(BaseModel):
    speakers: List[SpeakerInfo] = []


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    speaker: str


class TranscriptOutput(BaseModel):
    raw: str = ""
    confidence: float = 0.0
    language: str = "pt-BR"
    segments: List[TranscriptSegment] = []


class LinkedCode(BaseModel):
    system: str  # "ICD-10", "SNOMED-CT", "LOINC", "TUSS"
    code: str
    display: str


class ClinicalEntity(BaseModel):
    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: Literal["symptom", "diagnosis", "medication", "vital_sign", "procedure"]
    value: str
    confidence: float
    linked_code: Optional[LinkedCode] = None
    negated: bool = False
    temporal: Literal["present", "past", "family_history", "unknown"] = "present"


class ClinicalExtraction(BaseModel):
    entities: List[ClinicalEntity] = []


class SOAPNote(BaseModel):
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""


class EntityCorrection(BaseModel):
    entity_id: str
    original_value: str
    corrected_value: str
    correction_type: Literal["entity_edit", "entity_delete", "soap_edit", "entity_add"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditEntry(BaseModel):
    action: str
    actor_id: Optional[str] = None
    details: Optional[dict] = None
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Modelo Principal ─────────────────────────────────────────────────────────

class ClinicalSession(BaseModel):
    """
    Documento principal da sessão clínica (MongoDB).
    Status lifecycle: AWAITING_REVIEW → APPROVED → SYNCED | DISCARDED
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: Optional[str] = None
    doctor_id: Optional[str] = None
    specialty: Optional[str] = None  # "cardiology", "psychiatry", etc.

    # Áudio
    audio_url: Optional[str] = None  # S3/GCS encrypted
    audio_metadata: Optional[AudioMetadata] = None

    # Pipeline de processamento
    diarization: Optional[DiarizationOutput] = None
    transcript: Optional[TranscriptOutput] = None
    clinical_extraction: Optional[ClinicalExtraction] = None

    # SOAP + FHIR
    soap: Optional[SOAPNote] = None
    fhir_resources: Optional[dict] = None  # FHIR Bundle JSON

    # Confidence scores por código ontológico
    confidence_scores: dict = Field(default_factory=dict)

    # Revisão médica
    review_status: Literal[
        "AWAITING_REVIEW", "APPROVED", "REJECTED", "SYNCED", "DISCARDED", "FAILED"
    ] = "AWAITING_REVIEW"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    corrections: List[EntityCorrection] = []

    # Sync com PEP
    sync_status: Literal["PENDING", "SYNCED", "FAILED", "DISCARDED"] = "PENDING"
    synced_at: Optional[datetime] = None
    sync_attempts: int = 0
    sync_errors: List[str] = []
    fhir_ids: dict = Field(default_factory=dict)  # IDs retornados do EHR

    # Auditoria
    audit_trail: List[AuditEntry] = []

    # Metadados
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None  # TTL 30 dias
    version: str = "1.0"

    class Config:
        populate_by_name = True
