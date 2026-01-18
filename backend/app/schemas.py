from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class DiagramBase(BaseModel):
    name: str
    graph: Any


class DiagramCreate(DiagramBase):
    project_id: int


class DiagramUpdate(BaseModel):
    name: Optional[str] = None
    graph: Optional[Any] = None


class DiagramRead(DiagramBase):
    id: int
    project_id: int

    model_config = ConfigDict(from_attributes=True)


class PromptHistoryBase(BaseModel):
    prompt: str
    graph: Any


class PromptHistoryCreate(PromptHistoryBase):
    pass


class PromptHistoryRead(PromptHistoryBase):
    id: int
    user_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserBase(BaseModel):
    email: str


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: UserRead



