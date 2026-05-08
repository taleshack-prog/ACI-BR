"""
Audio Endpoints — WebSocket streaming + REST upload.

WebSocket /audio/stream:
  - Recebe chunks PCM base64
  - Acumula até ter ~3s de áudio (48 chunks de 100ms)
  - Envia para OpenAI Whisper API e retorna transcrição parcial
"""
import logging
import uuid
import base64
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.audio_service import transcribe_with_openai, process_audio_file
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

_sessions_store: dict = {}

CHUNKS_PER_BATCH = 30  # 30 chunks × 100ms = ~3s de áudio por transcrição parcial


@router.websocket("/stream")
async def audio_stream(websocket: WebSocket):
    """
    WebSocket de streaming de áudio com transcrição parcial via OpenAI Whisper.
    """
    await websocket.accept()
    session_id = None
    pending_chunks: list = []

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            session_id = message.get("sessionId")

            if msg_type == "start":
                _sessions_store[session_id] = {
                    "session_id": session_id,
                    "patient_id": message.get("patientId"),
                    "doctor_id": message.get("doctorId"),
                    "specialty": message.get("specialty", "general"),
                    "chunks": [],
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "status": "recording",
                    "full_transcript": "",
                }
                pending_chunks = []
                await websocket.send_json({
                    "type": "status",
                    "sessionId": session_id,
                    "status": "recording",
                    "message": "Gravação iniciada. ACI-BR escutando...",
                })
                logger.info(f"Stream iniciado: {session_id}")

            elif msg_type == "chunk":
                if session_id not in _sessions_store:
                    continue

                chunk_b64 = message.get("audio", "")
                if chunk_b64:
                    _sessions_store[session_id]["chunks"].append(chunk_b64)
                    pending_chunks.append(chunk_b64)

                    # A cada CHUNKS_PER_BATCH chunks, transcreve o batch
                    if len(pending_chunks) >= CHUNKS_PER_BATCH and settings.OPENAI_API_KEY:
                        try:
                            # Monta WAV mínimo a partir dos chunks PCM Int16
                            pcm_bytes = b"".join(base64.b64decode(c) for c in pending_chunks)
                            wav_bytes = _pcm_to_wav(pcm_bytes)

                            transcript = await transcribe_with_openai(wav_bytes, "chunk.wav")
                            partial_text = transcript.raw.strip()

                            if partial_text:
                                _sessions_store[session_id]["full_transcript"] += " " + partial_text
                                await websocket.send_json({
                                    "type": "transcript",
                                    "sessionId": session_id,
                                    "text": partial_text,
                                    "speaker": "unknown",
                                    "partial": True,
                                })
                        except Exception as e:
                            logger.warning(f"Transcrição parcial falhou: {e}")
                        finally:
                            pending_chunks = []

                    await websocket.send_json({
                        "type": "ack",
                        "sessionId": session_id,
                        "chunksReceived": len(_sessions_store[session_id]["chunks"]),
                    })

            elif msg_type == "end":
                if session_id in _sessions_store:
                    session = _sessions_store[session_id]
                    total_chunks = len(session["chunks"])
                    estimated_duration = total_chunks * 0.1

                    # Transcreve chunks pendentes finais
                    if pending_chunks and settings.OPENAI_API_KEY:
                        try:
                            pcm_bytes = b"".join(base64.b64decode(c) for c in pending_chunks)
                            wav_bytes = _pcm_to_wav(pcm_bytes)
                            transcript = await transcribe_with_openai(wav_bytes, "final.wav")
                            if transcript.raw.strip():
                                session["full_transcript"] += " " + transcript.raw.strip()
                                await websocket.send_json({
                                    "type": "transcript",
                                    "sessionId": session_id,
                                    "text": transcript.raw.strip(),
                                    "speaker": "unknown",
                                    "partial": False,
                                })
                        except Exception as e:
                            logger.warning(f"Transcrição final falhou: {e}")

                    await websocket.send_json({
                        "type": "status",
                        "sessionId": session_id,
                        "status": "processing",
                        "message": f"Gravação finalizada ({estimated_duration:.1f}s). Processando...",
                        "fullTranscript": session.get("full_transcript", "").strip(),
                    })
                    logger.info(f"Stream encerrado: {session_id} | {total_chunks} chunks")
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket desconectado: {session_id}")
    except Exception as e:
        logger.error(f"Erro no stream {session_id}: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1, bits: int = 16) -> bytes:
    """Encapsula PCM raw em WAV válido para a API do Whisper."""
    import struct
    data_size = len(pcm_bytes)
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE',
        b'fmt ', 16, 1, channels,
        sample_rate, sample_rate * channels * bits // 8,
        channels * bits // 8, bits,
        b'data', data_size,
    )
    return header + pcm_bytes


@router.post("/process/{session_id}")
async def process_audio(session_id: str):
    """Status do processamento de uma sessão."""
    session = _sessions_store.get(session_id)
    if not session:
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")
    return {
        "session_id": session_id,
        "status": session.get("status", "unknown"),
        "chunks": len(session.get("chunks", [])),
        "has_transcript": bool(session.get("full_transcript")),
    }


@router.get("/status/{session_id}")
async def get_status(session_id: str):
    session = _sessions_store.get(session_id)
    if not session:
        raise HTTPException(404, detail=f"Sessão {session_id} não encontrada.")
    return {
        "session_id": session_id,
        "status": session.get("status"),
        "full_transcript": session.get("full_transcript", ""),
    }
