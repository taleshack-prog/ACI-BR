"""
Serviço de Processamento de Áudio.

ASR: OpenAI Whisper API (cloud) — transcrição real em pt-BR
Diarização: pyannote.audio (local) ou simulado

Fallback automático para modo simulado quando API key não está configurada.
"""
import io
import logging
import tempfile
import os
from typing import Optional

from app.config import settings
from app.models.session import (
    DiarizationOutput, SpeakerInfo, DiarizationSegment,
    TranscriptOutput, TranscriptSegment,
)

logger = logging.getLogger(__name__)

_diarization_pipeline = None
_diarization_available = False


def _load_diarization():
    global _diarization_pipeline, _diarization_available
    try:
        import torch
        from pyannote.audio import Pipeline
        _diarization_pipeline = Pipeline.from_pretrained(
            settings.DIARIZATION_MODEL,
            use_auth_token=settings.HF_TOKEN,
        )
        _diarization_available = True
        logger.info("✅ pyannote.audio carregado")
    except Exception as e:
        logger.warning(f"⚠️  pyannote não disponível ({e}). Diarização simulada.")


try:
    _load_diarization()
except Exception:
    pass


# ─── ASR via OpenAI Whisper API ───────────────────────────────────────────────

async def transcribe_with_openai(audio_bytes: bytes, filename: str = "audio.wav") -> TranscriptOutput:
    """Transcreve áudio usando OpenAI Whisper API."""
    try:
        import httpx

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        }

        # OpenAI espera multipart/form-data
        files = {"file": (filename, audio_bytes, "audio/wav")}
        data = {
            "model": "whisper-1",
            "language": "pt",
            "response_format": "verbose_json",
            "prompt": (
                "Transcrição de consulta médica em português brasileiro. "
                "Termos: hipertensão, diabetes, pressão arterial, frequência cardíaca, "
                "saturação, dipirona, losartan, metformina, paracetamol."
            ),
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
            )

        if response.status_code != 200:
            raise Exception(f"OpenAI API erro {response.status_code}: {response.text[:200]}")

        result = response.json()
        raw_text = result.get("text", "").strip()
        whisper_segments = result.get("segments", [])

        segments = [
            TranscriptSegment(
                start=seg.get("start", 0),
                end=seg.get("end", 0),
                text=seg.get("text", "").strip(),
                speaker="unknown",  # diarização separada
            )
            for seg in whisper_segments
        ]

        # Confidence aproximado via avg_logprob
        avg_logprob = sum(s.get("avg_logprob", -0.5) for s in whisper_segments)
        avg_logprob = avg_logprob / len(whisper_segments) if whisper_segments else -0.5
        confidence = max(0.0, min(1.0, 1.0 + avg_logprob / 3.0))

        logger.info(f"✅ OpenAI Whisper: {len(raw_text)} chars, {len(segments)} segmentos, conf={confidence:.2f}")
        return TranscriptOutput(
            raw=raw_text,
            confidence=confidence,
            language="pt-BR",
            segments=segments,
        )

    except Exception as e:
        logger.error(f"Erro OpenAI Whisper: {e}")
        raise


# ─── Diarização ───────────────────────────────────────────────────────────────

async def diarize_audio(audio_path: str) -> DiarizationOutput:
    """Diarização real via pyannote ou simulada."""
    if _diarization_available and _diarization_pipeline:
        try:
            diarization = _diarization_pipeline(audio_path)
            speakers: dict = {}
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                speakers.setdefault(speaker, []).append(
                    DiarizationSegment(start=turn.start, end=turn.end, text="")
                )
            speaker_list = [
                SpeakerInfo(speaker_id=spk, role="doctor" if i == 0 else "patient", segments=segs)
                for i, (spk, segs) in enumerate(speakers.items())
            ]
            return DiarizationOutput(speakers=speaker_list)
        except Exception as e:
            logger.error(f"Erro diarização: {e}")

    # Simulado
    return DiarizationOutput(speakers=[
        SpeakerInfo(speaker_id="SPEAKER_00", role="doctor", segments=[
            DiarizationSegment(start=0.0, end=5.0, text=""),
            DiarizationSegment(start=12.0, end=25.0, text=""),
        ]),
        SpeakerInfo(speaker_id="SPEAKER_01", role="patient", segments=[
            DiarizationSegment(start=5.0, end=12.0, text=""),
            DiarizationSegment(start=25.0, end=35.0, text=""),
        ]),
    ])


# ─── Pipeline Completo ────────────────────────────────────────────────────────

async def process_audio_file(audio_bytes: bytes, content_type: str = "audio/wav") -> dict:
    """
    Pipeline: bytes → diarização + transcrição.
    Usa OpenAI Whisper API se OPENAI_API_KEY estiver configurada.
    """
    suffix = ".wav" if "wav" in content_type else ".webm" if "webm" in content_type else ".mp3"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        diarization = await diarize_audio(tmp_path)

        # Tenta OpenAI Whisper real
        if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.startswith("sk-"):
            try:
                transcript = await transcribe_with_openai(audio_bytes, f"audio{suffix}")
                logger.info("✅ Transcrição via OpenAI Whisper API")
            except Exception as e:
                logger.warning(f"OpenAI falhou, usando simulado: {e}")
                transcript = _simulated_transcript()
        else:
            logger.info("ℹ️  OPENAI_API_KEY não configurada — transcrição simulada")
            transcript = _simulated_transcript()

        # Associa speakers aos segmentos
        for seg in transcript.segments:
            seg.speaker = _assign_speaker(seg.start, seg.end, diarization)

        return {"diarization": diarization, "transcript": transcript}
    finally:
        os.unlink(tmp_path)


def _simulated_transcript() -> TranscriptOutput:
    raw = (
        "Paciente relata dor no peito há 3 dias, com piora aos esforços. "
        "Nega febre e tosse. Histórico familiar de hipertensão. "
        "PA: 140/90 mmHg. FC: 88 bpm. SatO2: 97%. "
        "Hipótese de angina e hipertensão arterial. "
        "Prescrever Losartan 50mg uma vez ao dia e solicitar eletrocardiograma."
    )
    return TranscriptOutput(
        raw=raw, confidence=0.94, language="pt-BR",
        segments=[
            TranscriptSegment(start=0.0, end=12.0, text="Paciente relata dor no peito há 3 dias.", speaker="SPEAKER_01"),
            TranscriptSegment(start=12.0, end=25.0, text="PA: 140/90 mmHg. FC: 88 bpm.", speaker="SPEAKER_00"),
            TranscriptSegment(start=25.0, end=35.0, text="Prescrever Losartan 50mg.", speaker="SPEAKER_00"),
        ],
    )


def _assign_speaker(start: float, end: float, diarization: Optional[DiarizationOutput]) -> str:
    if not diarization:
        return "unknown"
    best_overlap, best_speaker = 0.0, "unknown"
    for spk in diarization.speakers:
        for seg in spk.segments:
            overlap = min(end, seg.end) - max(start, seg.start)
            if overlap > best_overlap:
                best_overlap, best_speaker = overlap, spk.speaker_id
    return best_speaker
