from pydantic import BaseModel, EmailStr
from typing import Optional

class CreateUserDto(BaseModel):
    username: str
    first_name: str
    last_name: str
    email: EmailStr
    password: str

class UserDto(BaseModel):
    username: str
    first_name: str
    last_name: str
    email: EmailStr

    class Config:
        from_attributes = True

class LoginDto(BaseModel):
    username: str
    password: str 