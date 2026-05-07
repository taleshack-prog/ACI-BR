"""
Gerador de SOAP Semântico.

Classifica as entidades extraídas nos 4 eixos SOAP:
  S — Subjective  : queixas, sintomas relatados pelo paciente
  O — Objective   : sinais vitais, achados de exame físico
  A — Assessment  : diagnósticos, hipóteses (com CID-10)
  P — Plan        : medicações, procedimentos, encaminhamentos, retorno
"""
import logging
from typing import List, Optional
from app.models.session import ClinicalEntity, SOAPNote, TranscriptOutput, DiarizationOutput

logger = logging.getLogger(__name__)


def _get_patient_speech(diarization: Optional[DiarizationOutput]) -> str:
    """Extrai falas do paciente para popular o Subjective."""
    if not diarization:
        return ""
    lines = []
    for speaker in diarization.speakers:
        if speaker.role == "patient":
            for seg in speaker.segments:
                lines.append(seg.text)
    return " ".join(lines)


def _get_doctor_speech(diarization: Optional[DiarizationOutput]) -> str:
    """Extrai falas do médico para popular Objective e Plan."""
    if not diarization:
        return ""
    lines = []
    for speaker in diarization.speakers:
        if speaker.role == "doctor":
            for seg in speaker.segments:
                lines.append(seg.text)
    return " ".join(lines)


def generate_soap(
    entities: List[ClinicalEntity],
    transcript: Optional[TranscriptOutput] = None,
    diarization: Optional[DiarizationOutput] = None,
    specialty: str = "general",
) -> SOAPNote:
    """
    Gera nota SOAP estruturada a partir das entidades clínicas.

    Em produção: aumentar com LLM fine-tuned (ex: GPT-4o médico, Llama-Med-PT)
    que recebe o transcript completo e gera cada seção com linguagem médica fluente.
    Esta implementação produz SOAP a partir de templates + entidades.
    """
    symptoms = [e for e in entities if e.type == "symptom" and not e.negated]
    neg_symptoms = [e for e in entities if e.type == "symptom" and e.negated]
    diagnoses = [e for e in entities if e.type == "diagnosis"]
    vitals = [e for e in entities if e.type == "vital_sign"]
    medications = [e for e in entities if e.type == "medication"]

    patient_text = _get_patient_speech(diarization) if diarization else (transcript.raw if transcript else "")

    # ─── S: Subjective ────────────────────────────────────────────────────────
    subj_parts = []
    if symptoms:
        symptom_list = ", ".join(e.value for e in symptoms)
        subj_parts.append(f"Paciente relata: {symptom_list}.")
    if neg_symptoms:
        neg_list = ", ".join(e.value for e in neg_symptoms)
        subj_parts.append(f"Nega: {neg_list}.")
    if patient_text and not subj_parts:
        # fallback: primeiras 300 chars da fala do paciente
        subj_parts.append(patient_text[:300] + ("..." if len(patient_text) > 300 else ""))
    subjective = " ".join(subj_parts) if subj_parts else "Queixa principal não identificada automaticamente — revisar transcrição."

    # ─── O: Objective ─────────────────────────────────────────────────────────
    obj_parts = []
    if vitals:
        for v in vitals:
            code_info = f" ({v.linked_code.code})" if v.linked_code else ""
            obj_parts.append(f"{v.value}{code_info}")
    objective = "Sinais vitais: " + ", ".join(obj_parts) + "." if obj_parts else "Sinais vitais não registrados automaticamente — verificar prontuário."

    # ─── A: Assessment ────────────────────────────────────────────────────────
    asmt_parts = []
    for i, d in enumerate(diagnoses, 1):
        if d.linked_code:
            asmt_parts.append(f"{i}. {d.value.title()} ({d.linked_code.code} — {d.linked_code.display})")
        else:
            asmt_parts.append(f"{i}. {d.value.title()}")
    if not diagnoses and symptoms:
        # Se não há diagnóstico explícito, lista os sintomas como hipóteses abertas
        symptom_codes = [
            f"{s.value.title()} ({s.linked_code.code})" if s.linked_code else s.value.title()
            for s in symptoms
        ]
        asmt_parts.append("Hipótese diagnóstica a confirmar: " + ", ".join(symptom_codes))
    assessment = "\n".join(asmt_parts) if asmt_parts else "Avaliação pendente de revisão médica."

    # ─── P: Plan ──────────────────────────────────────────────────────────────
    plan_parts = []
    for i, m in enumerate(medications, 1):
        plan_parts.append(f"{i}. Prescrever {m.value}")
    if not plan_parts:
        plan_parts.append("Conduta a ser definida pelo médico.")
    plan = "\n".join(plan_parts)

    soap = SOAPNote(
        subjective=subjective,
        objective=objective,
        assessment=assessment,
        plan=plan,
    )

    logger.info(f"SOAP gerado | specialty={specialty} | entities={len(entities)}")
    return soap
