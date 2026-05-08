"""Testes do EHR write-back service."""
import pytest
import asyncio
from app.services.ehr_service import write_back_to_ehr, EHRTemporaryError

SAMPLE_BUNDLE = {
    "resourceType": "Bundle",
    "type": "transaction",
    "entry": [
        {"resource": {"resourceType": "Condition", "id": "cond-1"}, "request": {"method": "POST", "url": "Condition"}},
        {"resource": {"resourceType": "Observation", "id": "obs-1"}, "request": {"method": "POST", "url": "Observation"}},
        {"resource": {"resourceType": "MedicationRequest", "id": "med-1"}, "request": {"method": "POST", "url": "MedicationRequest"}},
    ]
}

@pytest.mark.asyncio
async def test_simulator_write_back_success():
    result = await write_back_to_ehr(SAMPLE_BUNDLE, "test-session-001", ehr_target="simulator")
    assert result["success"] is True
    assert result["attempts"] == 1
    assert "condition" in result["fhir_ids"] or "observation" in result["fhir_ids"]

@pytest.mark.asyncio
async def test_simulator_returns_fhir_ids():
    result = await write_back_to_ehr(SAMPLE_BUNDLE, "test-session-002", ehr_target="simulator")
    assert result["success"] is True
    total_resources = sum(len(v) for v in result["fhir_ids"].values())
    assert total_resources == 3

@pytest.mark.asyncio
async def test_simulator_includes_metadata():
    result = await write_back_to_ehr(SAMPLE_BUNDLE, "test-session-003", ehr_target="simulator")
    assert "synced_at" in result
    assert "ehr" in result
    assert result["ehr"] == "EHR Simulator (Dev)"

@pytest.mark.asyncio
async def test_write_back_with_empty_bundle():
    empty_bundle = {"resourceType": "Bundle", "type": "transaction", "entry": []}
    result = await write_back_to_ehr(empty_bundle, "test-session-004", ehr_target="simulator")
    assert result["success"] is True
    assert result["fhir_ids"] == {}
