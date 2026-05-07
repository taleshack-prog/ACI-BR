"""
Serviço de Inteligência Clínica (NLP/NLU).

Pipeline:
1. C-NER (Clinical Named Entity Recognition) via BioBERT pt-BR
2. Entity Linking → ICD-10, SNOMED-CT, LOINC, TUSS
3. Negation Detection (análise de dependência sintática)
4. Temporal Classification (present / past / family_history)
"""
import logging
import re
from typing import List, Optional
from app.models.session import ClinicalEntity, LinkedCode, ClinicalExtraction

logger = logging.getLogger(__name__)


# ─── Dicionários de Mapeamento (seed data — expandir com APIs terminológicas) ─

ICD10_MAP = {
    "hipertensão": ("I10", "Hipertensão essencial (primária)"),
    "hipertensão arterial": ("I10", "Hipertensão essencial (primária)"),
    "diabetes": ("E11.9", "Diabetes mellitus tipo 2 sem complicações"),
    "diabetes tipo 2": ("E11.9", "Diabetes mellitus tipo 2 sem complicações"),
    "angina": ("I20.0", "Angina instável"),
    "dor no peito": ("R07.9", "Dor torácica não especificada"),
    "dor torácica": ("R07.9", "Dor torácica não especificada"),
    "infarto": ("I21.9", "Infarto agudo do miocárdio não especificado"),
    "pneumonia": ("J18.9", "Pneumonia não especificada"),
    "asma": ("J45.9", "Asma não especificada"),
    "depressão": ("F32.9", "Episódio depressivo não especificado"),
    "ansiedade": ("F41.9", "Transtorno ansioso não especificado"),
}

SNOMED_MAP = {
    "dor no peito": ("29857009", "Chest pain"),
    "dor torácica": ("29857009", "Chest pain"),
    "febre": ("386661006", "Fever"),
    "dispneia": ("230145002", "Difficulty breathing"),
    "falta de ar": ("230145002", "Difficulty breathing"),
    "cefaleia": ("25064002", "Headache"),
    "tontura": ("404640003", "Dizziness"),
    "náusea": ("422587007", "Nausea"),
    "vômito": ("422400008", "Vomiting"),
    "tosse": ("49727002", "Cough"),
    "fadiga": ("84229001", "Fatigue"),
}

LOINC_MAP = {
    "pressão arterial": ("85354-9", "Blood pressure panel"),
    "pa": ("85354-9", "Blood pressure panel"),
    "frequência cardíaca": ("8867-4", "Heart rate"),
    "fc": ("8867-4", "Heart rate"),
    "saturação": ("59408-5", "Oxygen saturation"),
    "sato2": ("59408-5", "Oxygen saturation"),
    "temperatura": ("8310-5", "Body temperature"),
    "peso": ("29463-7", "Body weight"),
    "altura": ("8302-2", "Body height"),
    "glicemia": ("2339-0", "Glucose [Mass/volume] in Blood"),
    "hemoglobina": ("718-7", "Hemoglobin [Mass/volume] in Blood"),
}

NEGATION_PATTERNS = [
    r"\bneg[ao]\b", r"\bneg[ao]u\b", r"\bnega\b", r"\bnão (tem|apresenta|refere|relata)\b",
    r"\bausência de\b", r"\bsem\b", r"\bnenhum[a]?\b", r"\bdescart[ao]\b",
]

TEMPORAL_PAST_PATTERNS = [
    r"\bhistória de\b", r"\bante[s]? de\b", r"\bpassado\b", r"\bcrônico\b",
    r"\bprévio\b", r"\bcirurgia anterior\b",
]

TEMPORAL_FAMILY_PATTERNS = [
    r"\bhistória familiar\b", r"\bpai\b", r"\bmãe\b", r"\birmão\b",
    r"\bfamiliar\b", r"\bhereditário\b",
]


def _is_negated(context: str, term_pos: int, window: int = 80) -> bool:
    """Negação não atravessa fronteiras de frase (ponto, ponto-e-vírgula, newline)."""
    start = max(0, term_pos - window)
    preceding = context[start:term_pos]
    last_boundary = max(preceding.rfind('.'), preceding.rfind(';'), preceding.rfind('\n'))
    if last_boundary >= 0:
        preceding = preceding[last_boundary + 1:]
    preceding = preceding.lower()
    for pattern in NEGATION_PATTERNS:
        if re.search(pattern, preceding):
            return True
    return False


def _get_temporal(context: str, term_pos: int, window: int = 80) -> str:
    start = max(0, term_pos - window)
    surrounding = context[start:term_pos + window].lower()
    for p in TEMPORAL_FAMILY_PATTERNS:
        if re.search(p, surrounding):
            return "family_history"
    for p in TEMPORAL_PAST_PATTERNS:
        if re.search(p, surrounding):
            return "past"
    return "present"


def _link_entity(term: str, entity_type: str) -> Optional[LinkedCode]:
    """Tenta mapear um termo clínico para uma ontologia padrão."""
    term_lower = term.lower().strip()
    if entity_type == "diagnosis":
        if term_lower in ICD10_MAP:
            code, display = ICD10_MAP[term_lower]
            return LinkedCode(system="ICD-10", code=code, display=display)
        if term_lower in SNOMED_MAP:
            code, display = SNOMED_MAP[term_lower]
            return LinkedCode(system="SNOMED-CT", code=code, display=display)
    elif entity_type == "symptom":
        if term_lower in SNOMED_MAP:
            code, display = SNOMED_MAP[term_lower]
            return LinkedCode(system="SNOMED-CT", code=code, display=display)
        if term_lower in ICD10_MAP:
            code, display = ICD10_MAP[term_lower]
            return LinkedCode(system="ICD-10", code=code, display=display)
    elif entity_type == "vital_sign":
        if term_lower in LOINC_MAP:
            code, display = LOINC_MAP[term_lower]
            return LinkedCode(system="LOINC", code=code, display=display)
    return None


# ─── Padrões de Extração de Entidades ─────────────────────────────────────────

# Sinais vitais: "PA: 140/90", "FC 88 bpm", "SatO2 98%", "Temp 37.8°C"
VITAL_SIGN_PATTERNS = [
    (r"\bPA[:\s]+(\d{2,3}/\d{2,3})\s*(mmHg)?", "pressão arterial", "vital_sign"),
    (r"\bFC[:\s]+(\d{2,3})\s*(bpm)?", "frequência cardíaca", "vital_sign"),
    (r"\bSatO?2[:\s]+(\d{2,3})\s*%?", "saturação", "vital_sign"),
    (r"\b[Tt]emp[eratura]*[:\s]+(\d{2}[.,]\d)\s*°?C?", "temperatura", "vital_sign"),
    (r"\bpeso[:\s]+(\d{2,3}[.,]?\d*)\s*kg", "peso", "vital_sign"),
    (r"\baltura[:\s]+(\d{1}[.,]\d{2})\s*m?", "altura", "vital_sign"),
    (r"\bpressão arterial[:\s]+(\d{2,3}/\d{2,3})", "pressão arterial", "vital_sign"),
]

# Medicamentos com dosagem: "Losartan 50mg", "Dipirona 500mg", "Metformina 850mg"
MEDICATION_PATTERN = r"\b([A-Z][a-zçãõáéí]+(?:\s[a-z]+)?)\s+(\d+(?:\.\d+)?)\s*(mg|ml|g|mcg|UI)\b"

# Sintomas comuns
SYMPTOM_TERMS = list(SNOMED_MAP.keys())

# Diagnósticos
DIAGNOSIS_TERMS = list(ICD10_MAP.keys())


def extract_entities(transcript: str) -> ClinicalExtraction:
    """
    Pipeline C-NER: extrai entidades clínicas do transcript.

    Em produção: substituir por modelo BioBERT via HuggingFace Inference.
    Esta implementação usa regras como fallback/baseline.
    """
    entities: List[ClinicalEntity] = []
    text = transcript

    # 1. Sinais vitais
    for pattern, label, etype in VITAL_SIGN_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            value = f"{label}: {m.group(1)}"
            entities.append(ClinicalEntity(
                type=etype,
                value=value,
                confidence=0.91,
                linked_code=_link_entity(label, etype),
                negated=_is_negated(text, m.start()),
                temporal="present",
            ))

    # 2. Medicamentos
    for m in re.finditer(MEDICATION_PATTERN, text):
        name = m.group(1)
        dose = f"{m.group(2)} {m.group(3)}"
        entities.append(ClinicalEntity(
            type="medication",
            value=f"{name} {dose}",
            confidence=0.88,
            negated=_is_negated(text, m.start()),
            temporal=_get_temporal(text, m.start()),
        ))

    # 3. Sintomas
    for term in SYMPTOM_TERMS:
        pattern = rf"\b{re.escape(term)}\b"
        for m in re.finditer(pattern, text, re.IGNORECASE):
            entities.append(ClinicalEntity(
                type="symptom",
                value=term,
                confidence=0.82,
                linked_code=_link_entity(term, "symptom"),
                negated=_is_negated(text, m.start()),
                temporal=_get_temporal(text, m.start()),
            ))

    # 4. Diagnósticos
    for term in DIAGNOSIS_TERMS:
        pattern = rf"\b{re.escape(term)}\b"
        for m in re.finditer(pattern, text, re.IGNORECASE):
            entities.append(ClinicalEntity(
                type="diagnosis",
                value=term,
                confidence=0.85,
                linked_code=_link_entity(term, "diagnosis"),
                negated=_is_negated(text, m.start()),
                temporal=_get_temporal(text, m.start()),
            ))

    logger.info(f"C-NER extraiu {len(entities)} entidades do transcript.")
    return ClinicalExtraction(entities=entities)
