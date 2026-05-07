"""Processing pipeline endpoints."""
from fastapi import APIRouter
router = APIRouter()

@router.post("/diarization")
async def diarize(body: dict):
    return {"message": "TODO: pyannote.audio diarization"}

@router.post("/asr")
async def transcribe(body: dict):
    return {"message": "TODO: Whisper V3 fine-tuned pt-BR"}

@router.post("/clinical-ner")
async def clinical_ner(body: dict):
    from app.services.nlp_service import extract_entities
    text = body.get("text", "")
    result = extract_entities(text)
    return result.model_dump()

@router.post("/soap-generator")
async def soap_generator(body: dict):
    return {"message": "TODO: SOAP generation from entities"}
