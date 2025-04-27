import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query, Header
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import asyncio
import logging
import pickle
from typing import Dict
import certifi
from sqlalchemy.orm import Session
from passlib.context import CryptContext

# State and Auth
import state
import auth
from auth import get_current_user, create_access_token, get_token_header
from services.user_services import register_user, login_user
from dto import (
    CreateUserDto, UserDto, LoginDto, 
    ConversationDto, CreateConversationDto,
    MessageDto, SendMessageDto, ConversationStateDto,
    UpdateConversationStateDto
)

# Database and Models
from database import get_db, engine, SessionLocal
from models import Base, User


# Agency
from agency_swarm import Agency
from ClientManagementAgency.CEO import CEO
from ClientManagementAgency.Worker import Worker

load_dotenv(override=True)
os.environ["SSL_CERT_FILE"] = certifi.where()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(
    title="Mamba FastAPI Chat",
    description="A FastAPI application with WebSocket chat and user authentication",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Create database tables
Base.metadata.create_all(bind=engine)

def load_threads(conversation_id):
    return pickle.loads(state.threads.get(conversation_id, pickle.dumps({})))

def save_threads(conversation_id: str, threads: dict):
    state.threads[conversation_id] = pickle.dumps(threads)

def load_settings(conversation_id: str):
    return pickle.loads(state.settings.get(conversation_id, pickle.dumps([])))

def save_settings(conversation_id: str, settings: list):
    state.settings[conversation_id] = pickle.dumps(settings)

def load_shared_state(conversation_id: str):
    print(f"All shared states: {state.shared_states}")
    logger.info(f"Loading shared state for conversation {conversation_id}: {state.shared_states.get(conversation_id, {})}")
    return state.shared_states.get(conversation_id, {})

def save_shared_state(conversation_id: str, shared_state: dict):
    print(f"All shared states: {state.shared_states}")
    logger.info(f"Saving shared state for conversation {conversation_id}: {shared_state}")
    state.shared_states[conversation_id] = shared_state

@app.get("/", tags=["UI"])
async def get():
    return HTMLResponse(html)

@app.post("/register", response_model=UserDto, tags=["Authentication"])
async def register_user_endpoint(user_data: CreateUserDto, db=Depends(get_db)):
    """Register a new user."""
    return register_user(user_data, db)

@app.post("/login", tags=["Authentication"])
async def login_for_access_token(login_data: LoginDto, db=Depends(get_db)):
    """Login a user and return an access token."""
    return await login_user(login_data, db)

@app.post("/chat/{conversation_id}", tags=["Chat"])
async def chat_endpoint(
    conversation_id: str,
    request: dict,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.username} authenticated for conversation {conversation_id}")
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )

    # Get message from request
    message = request.get("message")
    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is required"
        )

    logger.info(f"Received message from client {current_user.username} for conversation {conversation_id}: {message}")

    # Initialize or load agency
    agency = None
    if conversation_id in state.conversations:
        try:
            ceo = CEO()
            worker = Worker()

            agency = Agency(
                [ceo, [ceo, worker]],
                shared_instructions='./ClientManagementAgency/agency_manifesto.md',
                threads_callbacks={
                    'load': lambda: load_threads(conversation_id),
                    'save': lambda threads: save_threads(conversation_id, threads),
                },
                settings_callbacks={
                    'load': lambda: load_settings(conversation_id),
                    'save': lambda settings: save_settings(conversation_id, settings),
                }
            )

            for k, v in load_shared_state(conversation_id).items():
                agency.shared_state.set(k, v)

            logger.info(f"Loaded existing agency state for conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Error loading state for {conversation_id}: {e}. Creating new agency.")

    if agency is None:
        ceo = CEO()
        worker = Worker()

        agency = Agency(
            [ceo, [ceo, worker]],
            shared_instructions='./ClientManagementAgency/agency_manifesto.md',
            threads_callbacks={
                'load': lambda: load_threads(conversation_id),
                'save': lambda threads: save_threads(conversation_id, threads),
            },
            settings_callbacks={
                'load': lambda: load_settings(conversation_id),
                'save': lambda settings: save_settings(conversation_id, settings),
            }
        )

        for k, v in load_shared_state(conversation_id).items():
            agency.shared_state.set(k, v)
        logger.info(f"Created new agency instance for conversation {conversation_id}")
        try:
            save_shared_state(conversation_id, agency.shared_state.data)
        except Exception as e:
            logger.error(f"Error saving initial state for {conversation_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initialize conversation state"
            )

    try:
        # Get completion from agency
        response = agency.get_completion(message=message)
        
        # Save updated state
        save_shared_state(conversation_id, agency.shared_state.data)
        
        return {"response": response}
    except Exception as e:
        logger.error(f"Error processing message for {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {str(e)}"
        )

if __name__ == "__main__":
    print("Starting FastAPI server...")
    print("Ensure .env file has OPENAI_API_KEY and SECRET_KEY")
    print(f"Default user: testuser (no password needed)")
    print("Access the chat interface at http://localhost:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 