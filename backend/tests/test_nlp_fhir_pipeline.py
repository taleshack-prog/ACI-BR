"""
Testes de integração — Pipeline NLP → FHIR

Testa o pipeline completo:
  transcript → C-NER → SOAP → FHIR Bundle
"""
import pytest
from app.services.nlp_service import extract_entities
from app.services.soap_service import generate_soap
from app.services.fhir_service import build_fhir_bundle


SAMPLE_TRANSCRIPT = """
Paciente relata dor no peito há 3 dias, com piora aos esforços.
Nega febre e tosse. Histórico familiar de hipertensão.
PA: 140/90 mmHg. FC: 88 bpm. SatO2: 97%.
Hipótese de angina e hipertensão arterial.
Prescrever Losartan 50mg uma vez ao dia.
Solicitar eletrocardiograma.
"""


def test_extract_entities_finds_vitals():
    result = extract_entities(SAMPLE_TRANSCRIPT)
    vital_types = [e.type for e in result.entities]
    assert "vital_sign" in vital_types


def test_extract_entities_finds_symptoms():
    result = extract_entities(SAMPLE_TRANSCRIPT)
    symptom_values = [e.value.lower() for e in result.entities if e.type == "symptom"]
    # dor no peito ou dor torácica deve ser detectado
    assert any("dor" in v for v in symptom_values)


def test_negation_detection():
    result = extract_entities(SAMPLE_TRANSCRIPT)
    # febre é negado no transcript
    febre_entities = [e for e in result.entities if "febre" in e.value.lower()]
    if febre_entities:
        assert febre_entities[0].negated is True


def test_medication_extraction():
    result = extract_entities(SAMPLE_TRANSCRIPT)
    meds = [e for e in result.entities if e.type == "medication"]
    assert len(meds) >= 1
    assert any("Losartan" in m.value for m in meds)


def test_soap_generation():
    extraction = extract_entities(SAMPLE_TRANSCRIPT)
    soap = generate_soap(extraction.entities, specialty="cardiology")
    assert soap.subjective
    assert soap.objective
    assert soap.assessment
    assert soap.plan


def test_fhir_bundle_generation():
    extraction = extract_entities(SAMPLE_TRANSCRIPT)
    soap = generate_soap(extraction.entities)
    bundle = build_fhir_bundle(
        soap=soap,
        entities=extraction.entities,
        patient_id="patient-test-123",
        encounter_id="encounter-test-456",
        doctor_id="doctor-test-789",
    )
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "transaction"
    assert len(bundle["entry"]) >= 1

    resource_types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert "DocumentReference" in resource_types


def test_fhir_bundle_contains_conditions_for_diagnoses():
    extraction = extract_entities(SAMPLE_TRANSCRIPT)
    soap = generate_soap(extraction.entities)
    bundle = build_fhir_bundle(soap, extraction.entities, "p1", "e1", "d1")

    resource_types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    # Deve haver pelo menos uma Condition (diagnóstico ou sintoma)
    assert "Condition" in resource_types


def test_icd10_linking():
    result = extract_entities("paciente com hipertensão arterial confirmada")
    diagnoses = [e for e in result.entities if e.type == "diagnosis" and e.linked_code]
    assert any(e.linked_code.system == "ICD-10" for e in diagnoses)
    assert any(e.linked_code.code == "I10" for e in diagnoses)
