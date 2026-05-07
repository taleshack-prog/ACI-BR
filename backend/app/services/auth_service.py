"""
Serviço de Autenticação — OAuth2 + JWT.

Fluxo:
  POST /auth/login           → retorna access_token + refresh_token
  POST /auth/refresh         → renova access_token via refresh_token
  GET  /auth/me              → retorna dados do usuário autenticado

JWT payload:
  { sub: doctor_id, role: "DOCTOR"|"ADMIN"|"AUDITOR", exp, iat }

Em produção: integrar com ICP-Brasil para assinatura digital de prescrições.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

# ─── Schemas ──────────────────────────────────────────────────────────────────

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos


class TokenPayload(BaseModel):
    sub: str          # doctor_id
    role: str         # "DOCTOR" | "ADMIN" | "AUDITOR"
    exp: datetime
    iat: datetime


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    crm: Optional[str] = None
    specialty: Optional[str] = None


# ─── Mock de usuários (substituir por PostgreSQL em prod) ─────────────────────

_MOCK_USERS = {
    "medico@aci-br.com": {
        "id": "doctor-001",
        "email": "medico@aci-br.com",
        "name": "Dr. Carlos Souza",
        "role": "DOCTOR",
        "crm": "CRM/SP 123456",
        "specialty": "cardiology",
        "hashed_password": pwd_context.hash("senha123"),
    },
    "admin@aci-br.com": {
        "id": "admin-001",
        "email": "admin@aci-br.com",
        "name": "Admin ACI",
        "role": "ADMIN",
        "hashed_password": pwd_context.hash("admin123"),
    },
}


# ─── Funções de Token ─────────────────────────────────────────────────────────

def _create_token(subject: str, role: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_token_pair(user_id: str, role: str) -> TokenPair:
    access_exp = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_exp = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return TokenPair(
        access_token=_create_token(user_id, role, access_exp),
        refresh_token=_create_token(user_id, role, refresh_exp),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def decode_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return TokenPayload(**payload)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido ou expirado: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─── Autenticação ─────────────────────────────────────────────────────────────

def authenticate_user(email: str, password: str) -> Optional[dict]:
    user = _MOCK_USERS.get(email)
    if not user:
        return None
    if not pwd_context.verify(password, user["hashed_password"]):
        return None
    return user


# ─── Dependency Injection ────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> TokenPayload:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação não fornecido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(credentials.credentials)


async def require_doctor(current_user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    if current_user.role not in ("DOCTOR", "ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a médicos.")
    return current_user


async def require_admin(current_user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a administradores.")
    return current_user
