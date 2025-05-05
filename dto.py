from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List, Set, Dict, Any, Type, TypeVar, Generic, ForwardRef
import re
import datetime
from datetime import datetime as dt

# Generic type for database models
T = TypeVar('T')

class BaseDto(BaseModel, Generic[T]):
    """Base DTO class with methods to convert between DTOs and database models."""
    
    @classmethod
    def from_orm(cls, db_model):
        """Convert a database model to a DTO."""
        return cls.model_validate(db_model)
    
    def to_orm_dict(self) -> dict:
        """Convert DTO to a dictionary suitable for ORM model creation."""
        return self.model_dump(exclude_unset=True)
    
    def update_orm_model(self, db_model: T) -> T:
        """Update an ORM model with values from this DTO."""
        for key, value in self.to_orm_dict().items():
            if hasattr(db_model, key):
                setattr(db_model, key, value)
        return db_model

class TokenData(BaseModel):
    """Data model for JWT token payload."""
    email: Optional[str] = None

class CreateUserDto(BaseDto):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    
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

class UserDto(BaseDto):
    first_name: str
    last_name: str
    email: EmailStr

    class Config:
        from_attributes = True

class LoginDto(BaseDto):
    email: EmailStr
    password: str

# New DTOs for concurrency features

class ConversationDto(BaseDto):
    id: str
    name: str
    user_email: str
    shared_state: Optional[Dict[str, Any]] = None
    threads: Optional[Dict[str, Any]] = None
    settings: Optional[List[Dict[str, Any]]] = None
    latest_message: Optional["MessageDto"] = None
    is_pinned: Optional[bool] = False
    
    model_config = {
        "arbitrary_types_allowed": True,
        "from_attributes": True
    }
    
    @staticmethod
    def from_db_model(model, participants=None, messages=None):
        return ConversationDto(
            id=model.id,
            name=model.name,
            created_at=model.created_at,
            updated_at=model.updated_at,
            participants=participants or [],
            messages=messages or [],
            shared_state=model.shared_state,
            threads=model.threads,
            settings=model.settings
        )
    
    @staticmethod
    def to_db_dict(dto_dict, exclude_fields=None):
        """Convert DTO dict to database dict."""
        if exclude_fields is None:
            exclude_fields = []
        
        db_dict = {k: v for k, v in dto_dict.items() if k not in exclude_fields}
        return db_dict

class CreateConversationDto(BaseDto):
    name: str
    
    def to_db_dict(self):
        """Convert to dict suitable for creating a Conversation model."""
        return {'name': self.name}

class MessageDto(BaseDto):
    conversation_id: str
    sender: Optional[str] = None
    content: str
    timestamp: Optional[str] = None
    id: Optional[str] = None
    is_from_agency: Optional[bool] = False
    
    @staticmethod
    def from_db_model(message):
        """Convert a Message database model to a MessageDto."""
        return MessageDto(
            id=str(message.id),
            conversation_id=message.conversation_id,
            sender=message.sender_email,
            content=message.content,
            is_from_agency=message.is_from_agency,
            timestamp=message.timestamp.isoformat() if message.timestamp else None
        )
    
    def to_db_dict(self):
        """Convert DTO to dict suitable for database."""
        result = {
            'conversation_id': self.conversation_id,
            'sender_email': self.sender,
            'content': self.content,
            'is_from_agency': self.is_from_agency
        }
        
        # Convert timestamp if present
        if self.timestamp:
            result['timestamp'] = dt.fromisoformat(self.timestamp)
            
        return result

class SendMessageDto(BaseDto):
    conversation_id: str
    content: str
    
    def to_db_dict(self, sender_email):
        """Convert to dict suitable for creating a Message model."""
        return {
            'conversation_id': self.conversation_id,
            'sender_email': sender_email,
            'content': self.content,
            'is_from_agency': False
        }

class ConversationStateDto(BaseDto):
    conversation_id: str
    active_users: List[str]
    messages: List[MessageDto]
    last_updated: Optional[str] = None

class UpdateConversationStateDto(BaseDto):
    """DTO for updating conversation state fields"""
    shared_state: Optional[Dict[str, Any]] = None
    threads: Optional[Dict[str, Any]] = None
    settings: Optional[List[Dict[str, Any]]] = None

class RenameConversationDto(BaseDto):
    """DTO for renaming a conversation"""
    name: str 