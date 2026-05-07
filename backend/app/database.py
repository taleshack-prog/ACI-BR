"""
Conexões de banco de dados — MongoDB (motor async) + PostgreSQL (SQLAlchemy async).
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# ─── MongoDB ──────────────────────────────────────────────────────────────────

_mongo_client: AsyncIOMotorClient | None = None


async def get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(settings.MONGODB_URL)
        logger.info("MongoDB conectado")
    return _mongo_client


async def get_mongo_db() -> AsyncIOMotorDatabase:
    client = await get_mongo_client()
    return client[settings.MONGODB_DB]


async def close_mongo():
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None


# ─── PostgreSQL ───────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.POSTGRES_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
