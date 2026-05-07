"""Auth Endpoints — OAuth2 + JWT."""
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from app.services.auth_service import (
    LoginRequest, TokenPair, UserOut,
    authenticate_user, create_token_pair, decode_token, get_current_user, TokenPayload,
)

router = APIRouter()

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest):
    user = authenticate_user(body.email, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha incorretos.")
    return create_token_pair(user["id"], user["role"])

@router.post("/refresh", response_model=TokenPair)
async def refresh_token(body: RefreshRequest):
    payload = decode_token(body.refresh_token)
    return create_token_pair(payload.sub, payload.role)

@router.get("/me", response_model=UserOut)
async def get_me(current_user: TokenPayload = Depends(get_current_user)):
    from app.services.auth_service import _MOCK_USERS
    user = next((u for u in _MOCK_USERS.values() if u["id"] == current_user.sub), None)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return UserOut(id=user["id"], email=user["email"], name=user["name"],
                   role=user["role"], crm=user.get("crm"), specialty=user.get("specialty"))
