from fastapi import APIRouter, status

from src.api.dependencies import DBSession
from src.api.schemas.auth import RegisterRequest, RegisterResponse
from src.services.auth_service import register_user

router = APIRouter()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: DBSession):
    api_key = await register_user(session, body.external_user_id)
    return RegisterResponse(api_key=api_key)
