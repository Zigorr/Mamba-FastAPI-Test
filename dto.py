from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
import re

class CreateUserDto(BaseModel):
    username: str
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9]+$', v):
            raise ValueError('Username must not contain spaces or special characters')
        return v
    
    @field_validator('first_name', 'last_name')
    @classmethod
    def validate_names(cls, v, info):
        if not re.match(r'^[a-zA-Z]+$', v):
            raise ValueError(f'{info.field_name} must contain only letters (no spaces, numbers, or special characters)')
        return v
    
    @field_validator('email')
    @classmethod
    def validate_email_domain(cls, v):
        if not v.endswith('@mamba.agency'):
            raise ValueError('Email must be from mamba.agency domain')
        return v
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if not re.match(r'^(?=.*[A-Z])(?=.*[0-9])(?!.*\s).+$', v):
            raise ValueError('Password must contain at least 1 capital letter, 1 number, and no spaces')
        return v

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