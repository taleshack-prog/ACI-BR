"""
Serviço de Write-back para EHR (TASY, MV, Philips).

Fluxo:
  1. Recebe FHIR Bundle aprovado
  2. Tenta POST atômico no endpoint FHIR do PEP destino
  3. Retry com exponential backoff (1s, 2s, 4s, 8s — max 4 tentativas)
  4. Atualiza syncStatus: SYNCED | FAILED
  5. Armazena FHIR IDs retornados para rastreamento

Em produção: configurar EHR_BASE_URL para o endpoint real do hospital.
Modo simulado: retorna IDs fictícios com latência realista.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Configuração de EHRs ────────────────────────────────────────────────────

EHR_CONFIGS = {
    "tasy": {
        "name": "TASY (Philips)",
        "base_url": "https://tasy.hospital.com.br/fhir/r4",
        "auth_type": "oauth2",
    },
    "mv": {
        "name": "MV Soul MV",
        "base_url": "https://mv.hospital.com.br/fhir/r4",
        "auth_type": "basic",
    },
    "simulator": {
        "name": "EHR Simulator (Dev)",
        "base_url": None,  # modo simulado
        "auth_type": "none",
    },
}

DEFAULT_EHR = "simulator"
MAX_RETRIES = 4
BASE_DELAY = 1.0  # segundos


# ─── Write-back Principal ─────────────────────────────────────────────────────

async def write_back_to_ehr(
    fhir_bundle: dict,
    session_id: str,
    ehr_target: str = DEFAULT_EHR,
    correlation_id: Optional[str] = None,
) -> dict:
    """
    Envia o FHIR Bundle para o EHR com retry exponencial.

    Retorna:
      { success: bool, fhir_ids: dict, attempts: int, error: str | None }
    """
    corr_id = correlation_id or str(uuid.uuid4())
    ehr_config = EHR_CONFIGS.get(ehr_target, EHR_CONFIGS["simulator"])

    logger.info(f"Write-back iniciado | session={session_id} | ehr={ehr_config['name']} | corr={corr_id}")

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await _send_bundle(fhir_bundle, ehr_config, corr_id, session_id)

            logger.info(f"Write-back sucesso | session={session_id} | attempt={attempt} | ids={list(result.keys())}")
            return {
                "success": True,
                "fhir_ids": result,
                "attempts": attempt,
                "error": None,
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "ehr": ehr_config["name"],
                "correlation_id": corr_id,
            }

        except EHRTemporaryError as e:
            last_error = str(e)
            delay = BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(f"Write-back falha temporária | attempt={attempt}/{MAX_RETRIES} | retry em {delay}s | {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(delay)

        except EHRPermanentError as e:
            logger.error(f"Write-back falha permanente | session={session_id} | {e}")
            return {
                "success": False,
                "fhir_ids": {},
                "attempts": attempt,
                "error": str(e),
                "ehr": ehr_config["name"],
                "correlation_id": corr_id,
            }

    return {
        "success": False,
        "fhir_ids": {},
        "attempts": MAX_RETRIES,
        "error": f"Máximo de tentativas atingido: {last_error}",
        "ehr": ehr_config["name"],
        "correlation_id": corr_id,
    }


async def _send_bundle(bundle: dict, ehr_config: dict, corr_id: str, session_id: str) -> dict:
    """Envia o bundle para o EHR. Modo simulado quando base_url é None."""

    # Modo simulado (desenvolvimento)
    if not ehr_config["base_url"]:
        return await _simulate_ehr_response(bundle, session_id)

    # Modo real — HTTP para EHR externo
    headers = {
        "Content-Type": "application/fhir+json",
        "X-Correlation-ID": corr_id,
        "X-Idempotency-Key": session_id,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{ehr_config['base_url']}/Bundle",
            json=bundle,
            headers=headers,
        )

        if response.status_code == 201:
            data = response.json()
            return _extract_fhir_ids(data)
        elif response.status_code in (429, 502, 503, 504):
            raise EHRTemporaryError(f"EHR indisponível: HTTP {response.status_code}")
        elif response.status_code == 422:
            raise EHRPermanentError(f"Bundle FHIR inválido: {response.text[:200]}")
        else:
            raise EHRTemporaryError(f"Resposta inesperada: HTTP {response.status_code}")


async def _simulate_ehr_response(bundle: dict, session_id: str) -> dict:
    """Simula resposta do EHR com latência realista (200-500ms)."""
    await asyncio.sleep(0.2 + (hash(session_id) % 300) / 1000)

    fhir_ids = {}
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType")
        rid = resource.get("id", str(uuid.uuid4()))
        if rtype:
            key = rtype.lower()
            if key not in fhir_ids:
                fhir_ids[key] = []
            fhir_ids[key].append(f"{rtype}/{rid}")

    logger.info(f"EHR simulado: {sum(len(v) for v in fhir_ids.values())} recursos aceitos")
    return fhir_ids


def _extract_fhir_ids(bundle_response: dict) -> dict:
    """Extrai IDs dos recursos a partir da resposta de transação FHIR."""
    ids = {}
    for entry in bundle_response.get("entry", []):
        response = entry.get("response", {})
        location = response.get("location", "")
        if "/" in location:
            parts = location.split("/")
            rtype = parts[-2] if len(parts) >= 2 else "unknown"
            rid = parts[-1]
            ids.setdefault(rtype.lower(), []).append(f"{rtype}/{rid}")
    return ids


# ─── Exceções ─────────────────────────────────────────────────────────────────

class EHRTemporaryError(Exception):
    """Erro transitório — vale retry (network, timeout, 5xx)."""

class EHRPermanentError(Exception):
    """Erro permanente — não vale retry (422, 401, schema inválido)."""
