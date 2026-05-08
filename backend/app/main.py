"""ACI-BR Backend — FastAPI Entry Point"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.error_middleware import ErrorHandlerMiddleware
from app.routes import auth, audio, process, fhir, session, health

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(name)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 ACI-BR Backend iniciando...")
    try:
        from app.database import get_mongo_db
        from app.services.session_repository import ensure_indexes
        db = await get_mongo_db()
        await ensure_indexes(db)
        logger.info("✅ MongoDB conectado e indexes criados")
    except Exception as e:
        logger.warning(f"⚠️  MongoDB não disponível: {e} — sessões em memória")
    yield
    logger.info("🛑 ACI-BR Backend encerrando...")
    try:
        from app.database import close_mongo
        await close_mongo()
    except Exception:
        pass


app = FastAPI(
    title="ACI-BR FHIR Bridge",
    description="Ambient Clinical Intelligence — HL7 FHIR R4 API para prontuários brasileiros",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(audio.router, prefix="/audio", tags=["Audio"])
app.include_router(process.router, prefix="/process", tags=["Processing"])
app.include_router(fhir.router, prefix="/fhir/r4", tags=["FHIR R4"])
app.include_router(session.router, prefix="/session", tags=["Session"])
