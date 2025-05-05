import logging
import os # Import os
from datetime import datetime, timedelta
from typing import Optional, List
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, EmailStr
import uuid

from database import get_db
from models import User
from dto import UserDto, CreateUserDto, TokenData, LoginDto
from repositories import UserRepository, ConversationRepository, MessageRepository
from auth import (
    create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES as _dummy_auth_expire, # Keep original import path for now
    SECRET_KEY as _dummy_auth_secret, ALGORITHM as _dummy_auth_algo # Avoid name clashes if defined elsewhere
)
from utils.email_utils import send_verification_email

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Security Configuration Loading ---
# Load from environment variables with defaults for local development (though defaults are less secure)
SECRET_KEY = os.getenv("SECRET_KEY", "a_very_default_and_insecure_secret_key_for_dev")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

if SECRET_KEY == "a_very_default_and_insecure_secret_key_for_dev":
    logger.warning("Using default SECRET_KEY. Set a strong SECRET_KEY environment variable for production.")
# --- End Security Configuration --- 

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

async def register_user(user_data: CreateUserDto, db: Session, request: Request) -> dict:
    """Register a new user and send verification email."""
    user_repo = UserRepository(db)
    hashed_password = pwd_context.hash(user_data.password)
    verification_token = str(uuid.uuid4()) # Generate a unique token

    try:
        user = user_repo.create_from_dto(user_data, hashed_password, verification_token)
        db.flush()

        # Send verification email
        base_url = str(request.base_url) # Get base URL from request
        try:
            await send_verification_email(user.email, verification_token, base_url)
        except ValueError as domain_error: # Catch the specific ValueError from domain check
            db.rollback()
            logger.warning(f"Denied registration due to email domain: {user_data.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(domain_error) # Use the error message from ValueError
            )
        except Exception as email_error:
             # Important: Rollback user creation if email fails
            db.rollback()
            logger.error(f"Failed to send verification email, rolling back user creation for {user_data.email}: {email_error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification email. Please try again."
            )
            
        db.commit() # Commit only after email is sent successfully
        
        return {"message": "User registered successfully. Please check your email to verify your account."}
        
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error during user registration for {user_data.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during registration."
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
    
    # Create access token using loaded config
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, 
        secret_key=SECRET_KEY, 
        algorithm=ALGORITHM, 
        expires_delta=access_token_expires
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
            reverse=True)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": userDto,
        "conversations": conversation_summaries
    }
