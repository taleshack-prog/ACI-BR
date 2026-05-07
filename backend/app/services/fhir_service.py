"""
Parser SOAP → FHIR R4 Bundle.

Converte a nota SOAP estruturada e as entidades clínicas em recursos FHIR R4 atômicos:
  - DocumentReference (nota SOAP completa)
  - Condition         (diagnósticos CID-10)
  - Observation       (sinais vitais LOINC)
  - MedicationRequest (prescrições TUSS)
"""
import base64
import logging
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from app.models.session import SOAPNote, ClinicalEntity

logger = logging.getLogger(__name__)

FHIR_VERSION = "4.0.1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ref(resource_type: str, resource_id: str) -> dict:
    return {"reference": f"{resource_type}/{resource_id}"}


# ─── Recursos Individuais ─────────────────────────────────────────────────────

def build_document_reference(
    soap: SOAPNote,
    patient_id: str,
    encounter_id: str,
    doctor_id: str,
    doc_id: Optional[str] = None,
) -> dict:
    """Gera o recurso DocumentReference com a nota SOAP em Base64."""
    soap_text = f"""SOAP Note — ACI-BR
===================
SUBJECTIVE:
{soap.subjective}

OBJECTIVE:
{soap.objective}

ASSESSMENT:
{soap.assessment}

PLAN:
{soap.plan}
"""
    encoded = base64.b64encode(soap_text.encode("utf-8")).decode("utf-8")

    return {
        "resourceType": "DocumentReference",
        "id": doc_id or str(uuid.uuid4()),
        "meta": {"profile": ["http://hl7.org/fhir/StructureDefinition/DocumentReference"]},
        "status": "current",
        "docStatus": "preliminary",
        "type": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "34108-1",
                "display": "Outpatient Note"
            }]
        },
        "subject": _ref("Patient", patient_id),
        "encounter": _ref("Encounter", encounter_id),
        "date": _now_iso(),
        "author": [_ref("Practitioner", doctor_id)],
        "title": "Nota Clínica — SOAP (ACI-BR)",
        "content": [{
            "attachment": {
                "contentType": "text/plain;charset=utf-8",
                "data": encoded,
                "title": "Nota SOAP gerada por IA — aguardando validação médica"
            }
        }],
        "context": {
            "encounter": [_ref("Encounter", encounter_id)]
        }
    }


def build_condition(
    entity: ClinicalEntity,
    patient_id: str,
    encounter_id: str,
    doctor_id: str,
) -> Optional[dict]:
    """Gera Condition para um diagnóstico com código ICD-10."""
    if entity.type not in ("diagnosis", "symptom"):
        return None

    coding = []
    if entity.linked_code:
        system_map = {
            "ICD-10": "http://hl7.org/fhir/sid/icd-10",
            "SNOMED-CT": "http://snomed.info/sct",
        }
        coding.append({
            "system": system_map.get(entity.linked_code.system, entity.linked_code.system),
            "code": entity.linked_code.code,
            "display": entity.linked_code.display,
        })
    coding.append({"display": entity.value})

    verification = "entered-in-error" if entity.negated else "provisional"

    return {
        "resourceType": "Condition",
        "id": str(uuid.uuid4()),
        "clinicalStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                "code": "active" if not entity.negated else "resolved"
            }]
        },
        "verificationStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                "code": verification
            }]
        },
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                "code": "encounter-diagnosis"
            }]
        }],
        "code": {
            "coding": coding,
            "text": entity.value,
        },
        "subject": _ref("Patient", patient_id),
        "encounter": _ref("Encounter", encounter_id),
        "recordedDate": _now_iso(),
        "recorder": _ref("Practitioner", doctor_id),
        "note": [{"text": f"Confidence: {entity.confidence:.0%} | Negated: {entity.negated}"}],
    }


def build_observation(
    entity: ClinicalEntity,
    patient_id: str,
    encounter_id: str,
    doctor_id: str,
) -> Optional[dict]:
    """Gera Observation para sinais vitais com código LOINC."""
    if entity.type != "vital_sign":
        return None
    if not entity.linked_code:
        return None

    obs = {
        "resourceType": "Observation",
        "id": str(uuid.uuid4()),
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "vital-signs",
                "display": "Vital Signs"
            }]
        }],
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": entity.linked_code.code,
                "display": entity.linked_code.display,
            }],
            "text": entity.value,
        },
        "subject": _ref("Patient", patient_id),
        "encounter": _ref("Encounter", encounter_id),
        "effectiveDateTime": _now_iso(),
        "performer": [_ref("Practitioner", doctor_id)],
        "valueString": entity.value,
        "note": [{"text": f"Extraído automaticamente pelo ACI-BR. Confidence: {entity.confidence:.0%}"}],
    }
    return obs


def build_medication_request(
    entity: ClinicalEntity,
    patient_id: str,
    encounter_id: str,
    doctor_id: str,
) -> Optional[dict]:
    """Gera MedicationRequest para prescrições detectadas."""
    if entity.type != "medication":
        return None

    return {
        "resourceType": "MedicationRequest",
        "id": str(uuid.uuid4()),
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "text": entity.value,
        },
        "subject": _ref("Patient", patient_id),
        "encounter": _ref("Encounter", encounter_id),
        "authoredOn": _now_iso(),
        "requester": _ref("Practitioner", doctor_id),
        "note": [{"text": f"Detectado automaticamente. Confidence: {entity.confidence:.0%}. REVISAR ANTES DE FINALIZAR."}],
    }


# ─── Bundle FHIR ─────────────────────────────────────────────────────────────

def build_fhir_bundle(
    soap: SOAPNote,
    entities: List[ClinicalEntity],
    patient_id: str,
    encounter_id: str,
    doctor_id: str,
) -> dict:
    """
    Constrói o FHIR Bundle de transação completo a partir do SOAP e entidades.
    """
    entries = []

    # DocumentReference
    doc_ref = build_document_reference(soap, patient_id, encounter_id, doctor_id)
    entries.append({"fullUrl": f"urn:uuid:{doc_ref['id']}", "resource": doc_ref,
                    "request": {"method": "POST", "url": "DocumentReference"}})

    for entity in entities:
        resource = None
        url = None

        if entity.type in ("diagnosis", "symptom"):
            resource = build_condition(entity, patient_id, encounter_id, doctor_id)
            url = "Condition"
        elif entity.type == "vital_sign":
            resource = build_observation(entity, patient_id, encounter_id, doctor_id)
            url = "Observation"
        elif entity.type == "medication":
            resource = build_medication_request(entity, patient_id, encounter_id, doctor_id)
            url = "MedicationRequest"

        if resource:
            entries.append({
                "fullUrl": f"urn:uuid:{resource['id']}",
                "resource": resource,
                "request": {"method": "POST", "url": url},
            })

    bundle = {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "type": "transaction",
        "timestamp": _now_iso(),
        "entry": entries,
    }

    logger.info(f"FHIR Bundle gerado: {len(entries)} entries (patient={patient_id})")
    return bundle
