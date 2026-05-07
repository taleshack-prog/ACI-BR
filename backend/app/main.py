"""
ACI-BR — Ambient Clinical Intelligence Backend
FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.error_middleware import ErrorHandlerMiddleware
from app.routes import auth, audio, process, fhir, session, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 ACI-BR Backend iniciando...")
    # TODO: inicializar conexões DB, carregar modelos ML
    yield
    logger.info("🛑 ACI-BR Backend encerrando...")


app = FastAPI(
    title="ACI-BR FHIR Bridge",
    description="Ambient Clinical Intelligence — HL7 FHIR R4 API para prontuários brasileiros",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── Middlewares ───────────────────────────────────────────────────────────────
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(audio.router, prefix="/audio", tags=["Audio"])
app.include_router(process.router, prefix="/process", tags=["Processing"])
app.include_router(fhir.router, prefix="/fhir/r4", tags=["FHIR R4"])
app.include_router(session.router, prefix="/session", tags=["Session"])
