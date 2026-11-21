"""Schemas de Pydantic: lo que entra y sale de la API.

Van separados de los modelos de SQLAlchemy (decisión del proyecto, no SQLModel):
la forma de la tabla y la forma de la API cambian por motivos distintos, y así
nunca se devuelve por error un campo interno como `hashed_password`.
"""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

# Email y username se guardan en minúsculas: "Ana" y "ana" son el mismo usuario.
Email = Annotated[EmailStr, Field(max_length=320), AfterValidator(str.lower)]
Username = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[A-Za-z0-9_-]{3,50}$"),
]
# 128 como máximo: Argon2 acepta más, pero limita el coste de un ataque con contraseñas enormes.
Password = Annotated[str, Field(min_length=8, max_length=128)]


class UserCreate(BaseModel):
    email: Email
    username: Username = Field(description="3-50 caracteres: letras, números, _ o -")
    password: Password


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # permite construirlo desde un User

    id: int
    email: str
    username: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="segundos hasta que caduca")
