"""Auth endpoints — OAuth2 + JWT."""
from fastapi import APIRouter
router = APIRouter()

@router.post("/login")
async def login(body: dict):
    # TODO: implementar auth_service com JWT
    return {"message": "TODO: implementar autenticação OAuth2 + JWT + ICP-Brasil"}
