from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    external_user_id: str = Field(
        ..., min_length=1, max_length=255, description="External user identifier"
    )


class RegisterResponse(BaseModel):
    api_key: str
    message: str = "User registered successfully. Save your API key — it won't be shown again."
