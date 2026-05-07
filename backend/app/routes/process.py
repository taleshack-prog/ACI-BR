"""Processing Pipeline Endpoints."""
import uuid
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional

from app.services.nlp_service import extract_entities
from app.services.soap_service import generate_soap
from app.services.fhir_service import build_fhir_bundle
from app.services.audio_service import process_audio_file

router = APIRouter()

class NERRequest(BaseModel):
    text: str
    specialty: Optional[str] = "general"

class SOAPRequest(BaseModel):
    text: str
    specialty: Optional[str] = "general"
    patient_id: Optional[str] = None
    encounter_id: Optional[str] = None
    doctor_id: Optional[str] = None

@router.post("/clinical-ner")
async def clinical_ner(body: NERRequest):
    """Extrai entidades clínicas com linking ICD-10/SNOMED-CT/LOINC."""
    return extract_entities(body.text).model_dump()

@router.post("/soap")
async def soap_generator(body: SOAPRequest):
    """Gera nota SOAP estruturada a partir do transcript."""
    extraction = extract_entities(body.text)
    soap = generate_soap(extraction.entities, specialty=body.specialty or "general")
    return {"soap": soap.model_dump(), "entities": extraction.model_dump(), "entity_count": len(extraction.entities)}

@router.post("/fhir-bundle")
async def generate_fhir(body: SOAPRequest):
    """Pipeline completo: texto → C-NER → SOAP → FHIR Bundle."""
    extraction = extract_entities(body.text)
    soap = generate_soap(extraction.entities, specialty=body.specialty or "general")
    bundle = build_fhir_bundle(
        soap=soap, entities=extraction.entities,
        patient_id=body.patient_id or "patient-unknown",
        encounter_id=body.encounter_id or str(uuid.uuid4()),
        doctor_id=body.doctor_id or "doctor-unknown",
    )
    return {"soap": soap.model_dump(), "fhir_bundle": bundle,
            "entity_count": len(extraction.entities), "fhir_resources": len(bundle["entry"])}

@router.post("/audio/{session_id}")
async def process_audio(session_id: str, file: UploadFile = File(...),
                        specialty: str = "general", patient_id: str = "patient-unknown",
                        encounter_id: Optional[str] = None):
    """Pipeline completo: áudio → diarização → ASR → C-NER → SOAP → FHIR Bundle."""
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(400, detail="Arquivo deve ser áudio (wav, mp3, webm).")
    audio_bytes = await file.read()
    result = await process_audio_file(audio_bytes, file.content_type)
    diarization = result["diarization"]
    transcript = result["transcript"]
    extraction = extract_entities(transcript.raw)
    soap = generate_soap(extraction.entities, transcript=transcript, diarization=diarization, specialty=specialty)
    enc_id = encounter_id or str(uuid.uuid4())
    bundle = build_fhir_bundle(soap=soap, entities=extraction.entities,
                               patient_id=patient_id, encounter_id=enc_id, doctor_id="doctor-from-auth")
    return {
        "session_id": session_id, "transcript": transcript.model_dump(),
        "diarization": diarization.model_dump(), "soap": soap.model_dump(),
        "fhir_bundle": bundle,
        "stats": {"duration_seconds": transcript.segments[-1].end if transcript.segments else 0,
                  "confidence": transcript.confidence, "entity_count": len(extraction.entities),
                  "fhir_resources": len(bundle["entry"]), "speakers": len(diarization.speakers)},
    }

@router.post("/diarization")
async def diarize(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    result = await process_audio_file(audio_bytes, file.content_type or "audio/wav")
    return result["diarization"].model_dump()

@router.post("/asr")
async def transcribe(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    result = await process_audio_file(audio_bytes, file.content_type or "audio/wav")
    return result["transcript"].model_dump()
