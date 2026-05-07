"""
Endpoints de Áudio — Streaming via WebSocket + REST.

  WebSocket /audio/stream — captura em tempo real (chunks PCM)
  POST      /audio/process/{session_id} — processamento assíncrono completo
  GET       /audio/status/{session_id}  — status do pipeline
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)

# Armazenamento temporário de sessões em andamento
_active_streams: dict = {}
_sessions_store: dict = {}  # compartilhado com session.py — usar DB em prod


class AudioProcessRequest(BaseModel):
    session_id: str
    patient_id: str
    doctor_id: str
    specialty: str = "general"


@router.websocket("/stream")
async def audio_stream(websocket: WebSocket):
    """
    WebSocket para streaming de áudio em tempo real.

    Protocolo esperado (JSON):
      { "type": "start", "sessionId": "uuid", "patientId": "...", "doctorId": "...", "specialty": "..." }
      { "type": "chunk", "sessionId": "uuid", "audio": "<base64 PCM>", "timestamp": 1234567890 }
      { "type": "end", "sessionId": "uuid" }

    Resposta (JSON):
      { "type": "transcript", "sessionId": "uuid", "text": "...", "speaker": "doctor|patient" }
      { "type": "status", "sessionId": "uuid", "status": "processing|ready" }
    """
    await websocket.accept()
    session_id = None

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            session_id = message.get("sessionId")

            if msg_type == "start":
                _active_streams[session_id] = {
                    "session_id": session_id,
                    "patient_id": message.get("patientId"),
                    "doctor_id": message.get("doctorId"),
                    "specialty": message.get("specialty", "general"),
                    "chunks": [],
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "status": "recording",
                }
                await websocket.send_json({
                    "type": "status",
                    "sessionId": session_id,
                    "status": "recording",
                    "message": "Gravação iniciada. ACI-BR escutando...",
                })
                logger.info(f"Sessão de áudio iniciada: {session_id}")

            elif msg_type == "chunk":
                if session_id in _active_streams:
                    chunk = message.get("audio", "")
                    _active_streams[session_id]["chunks"].append(chunk)

                    # TODO: enviar para pipeline de diarização/ASR em tempo real
                    # Em produção: pyannote VAD + Whisper streaming inference
                    await websocket.send_json({
                        "type": "ack",
                        "sessionId": session_id,
                        "chunksReceived": len(_active_streams[session_id]["chunks"]),
                    })

            elif msg_type == "end":
                if session_id in _active_streams:
                    stream_data = _active_streams.pop(session_id)
                    total_chunks = len(stream_data["chunks"])
                    estimated_duration = total_chunks * 0.1  # 100ms por chunk

                    # Cria sessão clínica para processamento
                    _sessions_store[session_id] = {
                        "session_id": session_id,
                        "patient_id": stream_data["patient_id"],
                        "doctor_id": stream_data["doctor_id"],
                        "specialty": stream_data["specialty"],
                        "audio_metadata": {
                            "duration": estimated_duration,
                            "sample_rate": 16000,
                            "channels": 1,
                            "format": "pcm/wav",
                        },
                        "review_status": "AWAITING_REVIEW",
                        "sync_status": "PENDING",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "audit_trail": [{
                            "action": "AUDIO_CAPTURED",
                            "details": {"chunks": total_chunks, "duration_sec": estimated_duration},
                            "at": datetime.now(timezone.utc).isoformat(),
                        }],
                    }

                    await websocket.send_json({
                        "type": "status",
                        "sessionId": session_id,
                        "status": "processing",
                        "message": f"Gravação finalizada ({estimated_duration:.1f}s). Processando...",
                        "totalChunks": total_chunks,
                    })
                    logger.info(f"Stream encerrado: {session_id} | {total_chunks} chunks | {estimated_duration:.1f}s")
                break

    except WebSocketDisconnect:
        if session_id and session_id in _active_streams:
            _active_streams.pop(session_id, None)
        logger.info(f"WebSocket desconectado: {session_id}")
    except Exception as e:
        logger.error(f"Erro no stream {session_id}: {e}")
        await websocket.send_json({"type": "error", "message": str(e)})


@router.post("/process/{session_id}")
async def process_audio(session_id: str, body: AudioProcessRequest):
    """
    Dispara o pipeline completo de processamento de áudio para uma sessão.
    Etapas: Diarização → ASR → C-NER → SOAP → FHIR Bundle

    Em produção: task assíncrona via Celery/ARQ.
    """
    # TODO: integrar com audio_service, nlp_service, soap_service, fhir_service
    return {
        "session_id": session_id,
        "status": "queued",
        "message": "Pipeline de processamento enfileirado.",
        "estimated_processing_time_seconds": 30,
    }


@router.get("/status/{session_id}")
async def get_processing_status(session_id: str):
    """Retorna o status atual do pipeline para uma sessão."""
    session = _sessions_store.get(session_id)
    if not session:
        # Verifica se ainda está em stream ativo
        if session_id in _active_streams:
            return {"session_id": session_id, "status": "recording"}
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")

    return {
        "session_id": session_id,
        "status": session.get("review_status", "AWAITING_REVIEW"),
        "has_soap": bool(session.get("soap")),
        "has_fhir_bundle": bool(session.get("fhir_resources")),
    }
