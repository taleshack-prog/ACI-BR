"""
FHIR R4 Endpoints — FHIR Bridge.
Base: /fhir/r4

Endpoints:
  POST /DocumentReference
  POST /Condition
  GET  /Condition
  POST /Observation
  POST /MedicationRequest
"""
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import Optional, List
import uuid

router = APIRouter()


# ─── Schemas de Request ───────────────────────────────────────────────────────

class FHIRResource(BaseModel):
    resourceType: str
    model_config = {"extra": "allow"}


class DocumentReferenceRequest(FHIRResource):
    resourceType: str = "DocumentReference"


class ConditionRequest(FHIRResource):
    resourceType: str = "Condition"


class ObservationRequest(FHIRResource):
    resourceType: str = "Observation"


class MedicationRequestResource(FHIRResource):
    resourceType: str = "MedicationRequest"


def _operation_outcome(severity: str, code: str, diagnostics: str) -> dict:
    return {
        "resourceType": "OperationOutcome",
        "issue": [{
            "severity": severity,
            "code": code,
            "diagnostics": diagnostics,
        }]
    }


def _created_response(resource: dict, resource_id: str) -> dict:
    resource["id"] = resource_id
    return resource


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/DocumentReference", status_code=201)
async def create_document_reference(
    body: DocumentReferenceRequest,
    x_correlation_id: Optional[str] = Header(None),
    x_idempotency_key: Optional[str] = Header(None),
):
    """
    Ingestão de nota clínica SOAP como DocumentReference FHIR.
    """
    if body.resourceType != "DocumentReference":
        raise HTTPException(422, detail=_operation_outcome(
            "error", "invalid", f"resourceType deve ser 'DocumentReference', recebido: {body.resourceType}"
        ))

    resource_id = str(uuid.uuid4())
    response = _created_response(body.model_dump(), resource_id)
    return response


@router.post("/Condition", status_code=201)
async def create_condition(
    body: ConditionRequest,
    x_correlation_id: Optional[str] = Header(None),
    x_idempotency_key: Optional[str] = Header(None),
):
    """
    Registro de diagnóstico (CID-10) como Condition FHIR.
    """
    if body.resourceType != "Condition":
        raise HTTPException(422, detail=_operation_outcome(
            "error", "invalid", "resourceType deve ser 'Condition'"
        ))
    resource_id = str(uuid.uuid4())
    return _created_response(body.model_dump(), resource_id)


@router.get("/Condition")
async def search_conditions(
    patient: Optional[str] = None,
    encounter: Optional[str] = None,
    code: Optional[str] = None,
    clinical_status: Optional[str] = None,
):
    """
    Busca de Conditions por paciente, encounter ou código CID-10.
    """
    # TODO: integrar com PostgreSQL
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": 0,
        "entry": [],
    }


@router.post("/Observation", status_code=201)
async def create_observation(
    body: ObservationRequest,
    x_correlation_id: Optional[str] = Header(None),
):
    """
    Registro de sinais vitais / sintomas como Observation FHIR.
    """
    if body.resourceType != "Observation":
        raise HTTPException(422, detail=_operation_outcome(
            "error", "invalid", "resourceType deve ser 'Observation'"
        ))
    resource_id = str(uuid.uuid4())
    return _created_response(body.model_dump(), resource_id)


@router.post("/MedicationRequest", status_code=201)
async def create_medication_request(
    body: MedicationRequestResource,
    x_correlation_id: Optional[str] = Header(None),
):
    """
    Registro de prescrição medicamentosa como MedicationRequest FHIR.
    """
    if body.resourceType != "MedicationRequest":
        raise HTTPException(422, detail=_operation_outcome(
            "error", "invalid", "resourceType deve ser 'MedicationRequest'"
        ))
    resource_id = str(uuid.uuid4())
    return _created_response(body.model_dump(), resource_id)


@router.post("/Bundle", status_code=201)
async def process_bundle(
    body: FHIRResource,
    x_correlation_id: Optional[str] = Header(None),
):
    """
    Processa um FHIR Bundle de transação completo (escrita atômica no PEP).
    """
    if body.resourceType != "Bundle":
        raise HTTPException(422, detail=_operation_outcome(
            "error", "invalid", "resourceType deve ser 'Bundle'"
        ))
    bundle_data = body.model_dump()
    entries = bundle_data.get("entry", [])

    # TODO: processar cada entry e persistir no PostgreSQL / EHR externo
    responses = []
    for entry in entries:
        res = entry.get("resource", {})
        res["id"] = str(uuid.uuid4())
        responses.append({
            "response": {"status": "201 Created", "location": f"{res.get('resourceType')}/{res['id']}"},
            "resource": res,
        })

    return {
        "resourceType": "Bundle",
        "type": "transaction-response",
        "entry": responses,
    }
