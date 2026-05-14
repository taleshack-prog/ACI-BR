"""
Serviço de Inteligência Clínica powered by Claude (Anthropic API).

Substitui o approach rule-based por Claude como motor de NLU médico.
Claude entende linguagem natural médica em pt-BR sem dicionário fixo,
detecta negações, temporalidade e mapeia para CID-10/SNOMED-CT/LOINC.
"""
import logging
import json
import httpx
from app.models.session import ClinicalEntity, LinkedCode, ClinicalExtraction, SOAPNote

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-sonnet-4-20250514"


async def _call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> str:
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(ANTHROPIC_API_URL, headers=headers, json=body)
        response.raise_for_status()
        return response.json()["content"][0]["text"]


def _parse_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


CNER_SYSTEM = """Você é um sistema especializado em extração de entidades clínicas médicas.
Analise o texto médico em português brasileiro e extraia TODAS as entidades clínicas.

Retorne APENAS um JSON array com objetos no formato:
{
  "type": "symptom" | "diagnosis" | "medication" | "vital_sign" | "procedure",
  "value": "termo como aparece no texto",
  "confidence": 0.0-1.0,
  "negated": true/false,
  "temporal": "present" | "past" | "family_history",
  "icd10_code": "código CID-10 ou null",
  "icd10_display": "descrição CID-10 ou null",
  "snomed_code": "código SNOMED-CT ou null",
  "snomed_display": "descrição em inglês ou null",
  "loinc_code": "código LOINC para sinais vitais/exames ou null",
  "loinc_display": "descrição LOINC ou null"
}

Regras importantes:
- Detecte negações: "nega", "não tem", "sem", "ausência de" — marque negated: true
- Negação NÃO atravessa ponto final
- Sinais vitais sempre com código LOINC
- Diagnósticos sempre com código CID-10
- Sintomas com código SNOMED-CT
- Retorne APENAS o JSON array, sem markdown"""


SOAP_SYSTEM = """Você é um assistente médico especializado em documentação clínica brasileira.
Gere uma nota SOAP estruturada em português a partir do transcript da consulta.

Retorne APENAS este JSON:
{
  "subjective": "Queixas, sintomas, história relatada pelo paciente",
  "objective": "Sinais vitais, exame físico, dados objetivos",
  "assessment": "Hipóteses diagnósticas com código CID-10 entre parênteses Ex: Gripe (J11.1)",
  "plan": "Medicações com dose, exames solicitados, orientações, retorno"
}

Use linguagem médica profissional em português brasileiro.
Retorne APENAS o JSON, sem texto adicional."""


async def extract_entities(transcript: str) -> ClinicalExtraction:
    """Extrai entidades clínicas via Claude API."""
    if not transcript.strip():
        return ClinicalExtraction(entities=[])

    try:
        response = await _call_claude(
            CNER_SYSTEM,
            f"Extraia as entidades clínicas:\n\n{transcript}",
        )
        raw = _parse_json(response)
        entities = []
        for e in raw:
            linked_code = None
            if e.get("loinc_code"):
                linked_code = LinkedCode(system="LOINC", code=e["loinc_code"], display=e.get("loinc_display", ""))
            elif e.get("snomed_code"):
                linked_code = LinkedCode(system="SNOMED-CT", code=e["snomed_code"], display=e.get("snomed_display", ""))
            elif e.get("icd10_code"):
                linked_code = LinkedCode(system="ICD-10", code=e["icd10_code"], display=e.get("icd10_display", ""))

            entities.append(ClinicalEntity(
                type=e.get("type", "symptom"),
                value=e.get("value", ""),
                confidence=float(e.get("confidence", 0.90)),
                linked_code=linked_code,
                negated=bool(e.get("negated", False)),
                temporal=e.get("temporal", "present"),
            ))
        logger.info(f"Claude C-NER: {len(entities)} entidades extraídas")
        return ClinicalExtraction(entities=entities)

    except Exception as e:
        logger.warning(f"Claude C-NER falhou ({e}), usando fallback")
        return _fallback_extract(transcript)


async def generate_soap(entities, transcript=None, diarization=None, specialty: str = "general") -> SOAPNote:
    """Gera nota SOAP via Claude."""
    transcript_text = ""
    if transcript and hasattr(transcript, 'raw'):
        transcript_text = transcript.raw
    elif isinstance(transcript, str):
        transcript_text = transcript

    entity_lines = []
    if entities:
        for e in entities:
            neg = " (NEGADO)" if e.negated else ""
            code = f" [{e.linked_code.system}: {e.linked_code.code}]" if e.linked_code else ""
            entity_lines.append(f"- {e.type}: {e.value}{neg}{code}")

    user_prompt = f"""Especialidade: {specialty}

Transcript:
{transcript_text or '(sem transcript)'}

Entidades extraídas:
{chr(10).join(entity_lines) if entity_lines else '(nenhuma)'}

Gere a nota SOAP."""

    try:
        response = await _call_claude(SOAP_SYSTEM, user_prompt, max_tokens=1500)
        soap_data = _parse_json(response)
        logger.info(f"Claude SOAP gerado | specialty={specialty}")
        return SOAPNote(
            subjective=soap_data.get("subjective", ""),
            objective=soap_data.get("objective", ""),
            assessment=soap_data.get("assessment", ""),
            plan=soap_data.get("plan", ""),
        )
    except Exception as e:
        logger.warning(f"Claude SOAP falhou ({e}), usando fallback")
        return _fallback_soap(entities, specialty)


def _fallback_extract(transcript: str) -> ClinicalExtraction:
    import re
    entities = []
    vital_patterns = [
        (r"\bPA[:\s]+(\d{2,3}/\d{2,3})", "pressão arterial", "vital_sign", "LOINC", "85354-9", "Blood pressure"),
        (r"\bFC[:\s]+(\d{2,3})", "frequência cardíaca", "vital_sign", "LOINC", "8867-4", "Heart rate"),
        (r"\bSatO?2[:\s]+(\d{2,3})", "saturação", "vital_sign", "LOINC", "59408-5", "Oxygen saturation"),
        (r"\b[Tt]emp[:\s]+(\d{2}[.,]\d)", "temperatura", "vital_sign", "LOINC", "8310-5", "Body temperature"),
    ]
    for pattern, label, etype, sys, code, display in vital_patterns:
        for m in re.finditer(pattern, transcript, re.IGNORECASE):
            entities.append(ClinicalEntity(
                type=etype, value=f"{label}: {m.group(1)}", confidence=0.90,
                linked_code=LinkedCode(system=sys, code=code, display=display),
                negated=False, temporal="present",
            ))
    logger.info(f"Fallback C-NER: {len(entities)} entidades")
    return ClinicalExtraction(entities=entities)


def _fallback_soap(entities, specialty: str) -> SOAPNote:
    symptoms = [e for e in entities if e.type == "symptom" and not e.negated]
    vitals = [e for e in entities if e.type == "vital_sign"]
    diagnoses = [e for e in entities if e.type == "diagnosis"]
    meds = [e for e in entities if e.type == "medication"]
    return SOAPNote(
        subjective="Paciente relata: " + ", ".join(e.value for e in symptoms) if symptoms else "Ver transcrição.",
        objective="Sinais vitais: " + ", ".join(e.value for e in vitals) if vitals else "Não registrado.",
        assessment="\n".join(f"{i+1}. {d.value} ({d.linked_code.code})" if d.linked_code else f"{i+1}. {d.value}" for i, d in enumerate(diagnoses)) if diagnoses else "Avaliação pendente.",
        plan="\n".join(f"{i+1}. Prescrever {m.value}" for i, m in enumerate(meds)) if meds else "Conduta a definir.",
    )
