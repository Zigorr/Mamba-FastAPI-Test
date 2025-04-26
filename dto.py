from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List, Set, Dict, Any, Type, TypeVar, Generic
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
    username: Optional[str] = None

class CreateUserDto(BaseDto):
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

class UserDto(BaseDto):
    username: str
    first_name: str
    last_name: str
    email: EmailStr

    class Config:
        from_attributes = True

class LoginDto(BaseDto):
    username: str
    password: str

# New DTOs for concurrency features

class ConversationDto(BaseDto):
    id: str
    name: str
    participants: List[str]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    @staticmethod
    def from_db_model(conversation, include_participants=True):
        """Convert a Conversation database model to a ConversationDto."""
        return ConversationDto(
            id=conversation.id,
            name=conversation.name,
            participants=[user.username for user in conversation.participants] if include_participants else [],
            created_at=conversation.created_at.isoformat() if conversation.created_at else None,
            updated_at=conversation.updated_at.isoformat() if conversation.updated_at else None
        )
    
    @staticmethod
    def to_db_dict(dto_dict, exclude_fields=None):
        """Convert DTO dict to database dict, excluding specified fields."""
        if exclude_fields is None:
            exclude_fields = ['participants', 'created_at', 'updated_at']
        
        db_dict = {k: v for k, v in dto_dict.items() if k not in exclude_fields}
        
        # Convert datetime strings to datetime objects
        if 'created_at' in dto_dict and dto_dict['created_at'] and 'created_at' not in exclude_fields:
            db_dict['created_at'] = dt.fromisoformat(dto_dict['created_at'])
        
        if 'updated_at' in dto_dict and dto_dict['updated_at'] and 'updated_at' not in exclude_fields:
            db_dict['updated_at'] = dt.fromisoformat(dto_dict['updated_at'])
        
        return db_dict

class CreateConversationDto(BaseDto):
    name: str
    participants: List[str]
    
    def to_db_dict(self):
        """Convert to dict suitable for creating a Conversation model."""
        return {'name': self.name}

class JoinConversationDto(BaseDto):
    conversation_id: str
    username: str

class LeaveConversationDto(BaseDto):
    conversation_id: str
    username: str

class MessageDto(BaseDto):
    conversation_id: str
    sender: str
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
            sender=message.sender_username,
            content=message.content,
            is_from_agency=message.is_from_agency,
            timestamp=message.timestamp.isoformat() if message.timestamp else None
        )
    
    def to_db_dict(self):
        """Convert DTO to dict suitable for database."""
        result = {
            'conversation_id': self.conversation_id,
            'sender_username': self.sender,
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
    
    def to_db_dict(self, sender_username):
        """Convert to dict suitable for creating a Message model."""
        return {
            'conversation_id': self.conversation_id,
            'sender_username': sender_username,
            'content': self.content,
            'is_from_agency': False
        }

class ConversationStateDto(BaseDto):
    conversation_id: str
    active_users: List[str]
    messages: List[MessageDto]
    last_updated: Optional[str] = None

class UserSessionDto(BaseDto):
    user_username: str
    conversation_id: str
    is_active: bool
    connected_at: Optional[str] = None
    disconnected_at: Optional[str] = None
    
    @staticmethod
    def from_db_model(session):
        """Convert a UserSession database model to a UserSessionDto."""
        return UserSessionDto(
            user_username=session.user_username,
            conversation_id=session.conversation_id,
            is_active=session.is_active,
            connected_at=session.connected_at.isoformat() if session.connected_at else None,
            disconnected_at=session.disconnected_at.isoformat() if session.disconnected_at else None
        )
    
    def to_db_dict(self):
        """Convert DTO to dict suitable for database."""
        result = {
            'user_username': self.user_username,
            'conversation_id': self.conversation_id,
            'is_active': self.is_active
        }
        
        # Convert datetime strings to datetime objects
        if self.connected_at:
            result['connected_at'] = dt.fromisoformat(self.connected_at)
        
        if self.disconnected_at:
            result['disconnected_at'] = dt.fromisoformat(self.disconnected_at)
            
        return result

class UserSessionsDto(BaseDto):
    username: str
    active_conversations: List[ConversationDto] 