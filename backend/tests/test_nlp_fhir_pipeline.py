"""
Testes do pipeline NLP → FHIR.
Com Claude como motor, testa fallback rule-based (sem API key nos testes).
"""
import pytest
from unittest.mock import patch, AsyncMock
from app.services.nlp_service import extract_entities, generate_soap, _fallback_extract, _fallback_soap
from app.services.fhir_service import build_fhir_bundle

SAMPLE_TRANSCRIPT = """
Paciente relata dor no peito há 3 dias, com piora aos esforços.
Nega febre e tosse. Histórico familiar de hipertensão.
PA: 140/90 mmHg. FC: 88 bpm. SatO2: 97%.
Hipótese de angina e hipertensão arterial.
Prescrever Losartan 50mg uma vez ao dia.
"""

# Testa fallback rule-based diretamente (sem chamar Claude)
def test_fallback_extract_finds_vitals():
    result = _fallback_extract(SAMPLE_TRANSCRIPT)
    vital_types = [e.type for e in result.entities]
    assert "vital_sign" in vital_types

def test_fallback_extract_finds_bp():
    result = _fallback_extract(SAMPLE_TRANSCRIPT)
    values = [e.value.lower() for e in result.entities]
    assert any("pressão" in v or "140" in v for v in values)

def test_fallback_soap_generates_sections():
    extraction = _fallback_extract(SAMPLE_TRANSCRIPT)
    soap = _fallback_soap(extraction.entities, "cardiology")
    assert soap.subjective or soap.objective or soap.assessment or soap.plan

def test_fhir_bundle_from_fallback():
    extraction = _fallback_extract(SAMPLE_TRANSCRIPT)
    soap = _fallback_soap(extraction.entities, "general")
    bundle = build_fhir_bundle(
        soap=soap, entities=extraction.entities,
        patient_id="p1", encounter_id="e1", doctor_id="d1",
    )
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "transaction"
    assert len(bundle["entry"]) >= 1

def test_fhir_bundle_has_document_reference():
    extraction = _fallback_extract(SAMPLE_TRANSCRIPT)
    soap = _fallback_soap(extraction.entities, "general")
    bundle = build_fhir_bundle(soap, extraction.entities, "p1", "e1", "d1")
    types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert "DocumentReference" in types

# Testa extract_entities com mock do Claude
@pytest.mark.asyncio
async def test_extract_entities_with_mock_claude():
    mock_response = '''[
        {"type": "symptom", "value": "dor no peito", "confidence": 0.95, "negated": false, "temporal": "present",
         "snomed_code": "29857009", "snomed_display": "Chest pain", "icd10_code": null, "loinc_code": null},
        {"type": "symptom", "value": "febre", "confidence": 0.92, "negated": true, "temporal": "present",
         "snomed_code": "386661006", "snomed_display": "Fever", "icd10_code": null, "loinc_code": null},
        {"type": "vital_sign", "value": "PA: 140/90", "confidence": 0.98, "negated": false, "temporal": "present",
         "loinc_code": "85354-9", "loinc_display": "Blood pressure", "icd10_code": null, "snomed_code": null},
        {"type": "medication", "value": "Losartan 50mg", "confidence": 0.96, "negated": false, "temporal": "present",
         "icd10_code": null, "snomed_code": null, "loinc_code": null}
    ]'''
    with patch('app.services.nlp_service._call_claude', new_callable=AsyncMock, return_value=mock_response):
        result = await extract_entities(SAMPLE_TRANSCRIPT)
    assert len(result.entities) == 4
    febre = next(e for e in result.entities if "febre" in e.value.lower())
    assert febre.negated is True
    dor = next(e for e in result.entities if "dor" in e.value.lower())
    assert dor.negated is False

@pytest.mark.asyncio
async def test_generate_soap_with_mock_claude():
    mock_response = '''{
        "subjective": "Paciente relata dor no peito há 3 dias.",
        "objective": "PA: 140/90 mmHg, FC: 88 bpm, SatO2: 97%",
        "assessment": "1. Angina pectoris (I20.0)\\n2. Hipertensão arterial (I10)",
        "plan": "1. Losartan 50mg 1x/dia\\n2. Solicitar ECG"
    }'''
    with patch('app.services.nlp_service._call_claude', new_callable=AsyncMock, return_value=mock_response):
        extraction = _fallback_extract(SAMPLE_TRANSCRIPT)
        soap = await generate_soap(extraction.entities, transcript=SAMPLE_TRANSCRIPT)
    assert "dor" in soap.subjective.lower() or "140" in soap.objective
    assert "I20" in soap.assessment or "I10" in soap.assessment
    assert "Losartan" in soap.plan

@pytest.mark.asyncio  
async def test_icd10_in_assessment():
    mock_response = '''{
        "subjective": "test",
        "objective": "test",
        "assessment": "Hipertensão arterial (I10)",
        "plan": "Losartan 50mg"
    }'''
    with patch('app.services.nlp_service._call_claude', new_callable=AsyncMock, return_value=mock_response):
        soap = await generate_soap([], transcript="hipertensão")
    assert "I10" in soap.assessment

@pytest.mark.asyncio
async def test_negation_via_claude():
    mock_response = '''[
        {"type": "symptom", "value": "febre", "confidence": 0.95, "negated": true, 
         "temporal": "present", "snomed_code": "386661006", "snomed_display": "Fever",
         "icd10_code": null, "loinc_code": null}
    ]'''
    with patch('app.services.nlp_service._call_claude', new_callable=AsyncMock, return_value=mock_response):
        result = await extract_entities("Nega febre.")
    assert result.entities[0].negated is True
