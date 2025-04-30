import logging
from datetime import datetime, timedelta
from typing import Optional, List
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import User
from dto import UserDto, CreateUserDto, TokenData, LoginDto
from repositories import UserRepository, ConversationRepository, MessageRepository
from auth import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Security configuration
SECRET_KEY = "your-secret-key"  # In production, use a secure random key
ALGORITHM = "HS256"

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def register_user(user_data: CreateUserDto, db: Session) -> UserDto:
    """Register a new user."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Check if email already exists
    if user_repo.get_by_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create hashed password
    hashed_password = pwd_context.hash(user_data.password)
    
    # Create user using repository
    user = user_repo.create_from_dto(user_data, hashed_password)
    
    # Return user DTO
    return UserDto(
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name
    )

def authenticate_user(email: str, password: str, db: Session) -> Optional[User]:
    """Authenticate a user by email and password."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Get user
    user = user_repo.get_by_email(email)
    
    # Verify password if user exists
    if not user or not pwd_context.verify(password, user.password):
        return None
    
    return user

def get_user_by_email(email: str, db: Session) -> Optional[UserDto]:
    """Get a user by email."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Get user
    user = user_repo.get_by_email(email)
    
    if not user:
        return None
    
    # Return user DTO
    return UserDto(
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name
    )

def get_users(db: Session, skip: int = 0, limit: int = 50) -> List[UserDto]:
    """Get a list of users."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Get users
    users = user_repo.get_all()
    
    # Convert to DTOs
    return [
        UserDto(
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name
        )
        for user in users
    ]

def update_user(email: str, user_data: dict, db: Session) -> Optional[UserDto]:
    """Update a user's information."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Get user
    user = user_repo.get_by_email(email)
    
    if not user:
        return None
    
    # Update user
    updated_user = user_repo.update(user, user_data)
    
    # Return user DTO
    return UserDto(
        email=updated_user.email,
        first_name=updated_user.first_name,
        last_name=updated_user.last_name
    )

def delete_user(email: str, db: Session) -> bool:
    """Delete a user."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Delete user
    return user_repo.delete(email)

async def login_user(login_data: LoginDto, db: Session) -> dict:
    """Authenticate user and return JWT token."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Get user
    user = user_repo.get_by_email(login_data.email)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify password
    if not pwd_context.verify(login_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    userDto = UserDto(
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    # Get user's conversations
    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)
    
    conversations = conversation_repo.get_for_user(user.email, limit=50)
    conversation_summaries = []
    
    for conversation in conversations:
        # Include ID, name and updated_at for sorting
        conversation_summaries.append({
            "id": conversation.id,
            "name": conversation.name,
            "updated_at": conversation.updated_at
        })
        # Sort conversations by updated_at after loop
        conversation_summaries = sorted(conversation_summaries, 
            key=lambda x: x["updated_at"], 
            reverse=False)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": userDto,
        "conversations": conversation_summaries
    } 