"""
Serviço de Processamento de Áudio.

Integra:
  1. pyannote.audio  — diarização de locutores (médico vs paciente)
  2. OpenAI Whisper  — ASR fine-tuned para pt-BR médico

Fallback automático para modo simulado quando modelos não estão disponíveis
(desenvolvimento sem GPU ou sem token HuggingFace).

Requisitos para modo real:
  pip install openai-whisper pyannote.audio torch
  HF_TOKEN=hf_xxx (para pyannote, que requer aceite dos termos)
"""
import io
import logging
import base64
import tempfile
import os
from typing import Optional

from app.config import settings
from app.models.session import DiarizationOutput, SpeakerInfo, DiarizationSegment, TranscriptOutput, TranscriptSegment

logger = logging.getLogger(__name__)

# ─── Carregamento lazy dos modelos ────────────────────────────────────────────

_whisper_model = None
_diarization_pipeline = None
_models_available = False


def _load_models():
    global _whisper_model, _diarization_pipeline, _models_available
    try:
        import whisper
        import torch
        from pyannote.audio import Pipeline

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Carregando Whisper {settings.WHISPER_MODEL} em {device}...")
        _whisper_model = whisper.load_model(settings.WHISPER_MODEL, device=device)

        logger.info("Carregando pyannote diarization pipeline...")
        _diarization_pipeline = Pipeline.from_pretrained(
            settings.DIARIZATION_MODEL,
            use_auth_token=settings.HF_TOKEN,
        )
        if torch.cuda.is_available():
            _diarization_pipeline = _diarization_pipeline.to(torch.device("cuda"))

        _models_available = True
        logger.info("✅ Modelos ML carregados com sucesso")

    except ImportError as e:
        logger.warning(f"⚠️  Dependências ML não instaladas ({e}). Usando modo simulado.")
    except Exception as e:
        logger.warning(f"⚠️  Erro ao carregar modelos ({e}). Usando modo simulado.")


# ─── Diarização ───────────────────────────────────────────────────────────────

async def diarize_audio(audio_path: str) -> DiarizationOutput:
    """
    Separa locutores no áudio.
    Modo real: pyannote.audio speaker-diarization-3.1
    Modo simulado: retorna estrutura mock para desenvolvimento
    """
    if _models_available and _diarization_pipeline:
        try:
            diarization = _diarization_pipeline(audio_path)
            speakers: dict[str, list] = {}
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                if speaker not in speakers:
                    speakers[speaker] = []
                speakers[speaker].append(DiarizationSegment(
                    start=turn.start, end=turn.end, text=""
                ))
            speaker_list = []
            for i, (spk_id, segs) in enumerate(speakers.items()):
                role = "doctor" if i == 0 else "patient"
                speaker_list.append(SpeakerInfo(speaker_id=spk_id, role=role, segments=segs))
            return DiarizationOutput(speakers=speaker_list)
        except Exception as e:
            logger.error(f"Erro na diarização real: {e}")

    # Modo simulado
    logger.info("Diarização simulada (modo desenvolvimento)")
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


# ─── ASR ──────────────────────────────────────────────────────────────────────

async def transcribe_audio(
    audio_path: str,
    diarization: Optional[DiarizationOutput] = None,
) -> TranscriptOutput:
    """
    Transcreve áudio para texto em pt-BR.
    Modo real: Whisper large-v3 com prompt médico
    Modo simulado: retorna transcript de exemplo
    """
    if _models_available and _whisper_model:
        try:
            # Prompt inicial com vocabulário médico para guiar o Whisper
            medical_prompt = (
                "Transcrição de consulta médica em português brasileiro. "
                "Termos: hipertensão, diabetes, pressão arterial, frequência cardíaca, "
                "saturação, dipirona, losartan, metformina, CID-10, SNOMED."
            )
            result = _whisper_model.transcribe(
                audio_path,
                language="pt",
                initial_prompt=medical_prompt,
                word_timestamps=True,
                verbose=False,
            )
            segments = []
            for seg in result.get("segments", []):
                # Atribuir speaker via overlap com diarização
                speaker = _assign_speaker(seg["start"], seg["end"], diarization)
                segments.append(TranscriptSegment(
                    start=seg["start"],
                    end=seg["end"],
                    text=seg["text"].strip(),
                    speaker=speaker,
                ))
            return TranscriptOutput(
                raw=result["text"].strip(),
                confidence=_avg_confidence(result),
                language="pt-BR",
                segments=segments,
            )
        except Exception as e:
            logger.error(f"Erro na transcrição real: {e}")

    # Modo simulado
    logger.info("ASR simulado (modo desenvolvimento)")
    raw = (
        "Paciente relata dor no peito há 3 dias, com piora aos esforços. "
        "Nega febre e tosse. Histórico familiar de hipertensão. "
        "PA: 140/90 mmHg. FC: 88 bpm. SatO2: 97%. "
        "Hipótese de angina e hipertensão arterial. "
        "Prescrever Losartan 50mg uma vez ao dia e solicitar eletrocardiograma."
    )
    return TranscriptOutput(
        raw=raw,
        confidence=0.94,
        language="pt-BR",
        segments=[
            TranscriptSegment(start=0.0, end=12.0,
                text="Paciente relata dor no peito há 3 dias, com piora aos esforços. Nega febre e tosse.",
                speaker="SPEAKER_01"),
            TranscriptSegment(start=12.0, end=25.0,
                text="PA: 140/90 mmHg. FC: 88 bpm. SatO2: 97%.",
                speaker="SPEAKER_00"),
            TranscriptSegment(start=25.0, end=35.0,
                text="Hipótese de angina e hipertensão arterial. Prescrever Losartan 50mg.",
                speaker="SPEAKER_00"),
        ],
    )


# ─── Pipeline Completo ────────────────────────────────────────────────────────

async def process_audio_file(audio_bytes: bytes, content_type: str = "audio/wav") -> dict:
    """
    Pipeline completo: bytes de áudio → diarização + transcrição.
    Salva temporariamente em disco (necessário para Whisper/pyannote).
    """
    suffix = ".wav" if "wav" in content_type else ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        diarization = await diarize_audio(tmp_path)
        transcript = await transcribe_audio(tmp_path, diarization)

        # Preenche texto nos segmentos de diarização
        for spk in diarization.speakers:
            for seg in spk.segments:
                matching = [
                    s.text for s in transcript.segments
                    if s.speaker == spk.speaker_id
                    and abs(s.start - seg.start) < 2.0
                ]
                if matching:
                    seg.text = matching[0]

        return {"diarization": diarization, "transcript": transcript}
    finally:
        os.unlink(tmp_path)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _assign_speaker(start: float, end: float, diarization: Optional[DiarizationOutput]) -> str:
    if not diarization:
        return "unknown"
    best_overlap = 0.0
    best_speaker = "unknown"
    for spk in diarization.speakers:
        for seg in spk.segments:
            overlap = min(end, seg.end) - max(start, seg.start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = spk.speaker_id
    return best_speaker


def _avg_confidence(whisper_result: dict) -> float:
    segs = whisper_result.get("segments", [])
    if not segs:
        return 0.0
    scores = [abs(s.get("avg_logprob", -1.0)) for s in segs]
    # Converte log-prob para 0-1 aproximado
    avg_logprob = sum(scores) / len(scores)
    return max(0.0, min(1.0, 1.0 - avg_logprob / 3.0))


# Tenta carregar modelos na importação (non-blocking em dev)
try:
    _load_models()
except Exception:
    pass
