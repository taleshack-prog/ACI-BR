"""Global error handler — retorna OperationOutcome FHIR em erros."""
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            logger.exception(f"Erro não tratado: {e}")
            return JSONResponse(status_code=500, content={
                "resourceType": "OperationOutcome",
                "issue": [{"severity": "fatal", "code": "exception", "diagnostics": str(e)}]
            })
