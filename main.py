import uvicorn
from fastapi import FastAPI, WebSocket, Depends, Query, Path, Body, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import logging
import certifi
from typing import List, Optional

# Database and Models
from database import engine, get_db
from models import Base

# Imported modules
from auth import get_current_user
from user_service import register_user, login_user
from chat import handle_websocket_chat
from dto import (
    CreateUserDto, UserDto, LoginDto, 
    ConversationDto, CreateConversationDto, JoinConversationDto, LeaveConversationDto,
    MessageDto, SendMessageDto, ConversationStateDto
)

# New services
import conversation_service
import agency_service

load_dotenv(override=True)
os.environ["SSL_CERT_FILE"] = certifi.where()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Mamba FastAPI Chat",
    description="A FastAPI application with WebSocket chat and user authentication",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, specify your frontend domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables
Base.metadata.create_all(bind=engine)

# Setup templates and OAuth2
templates = Jinja2Templates(directory="templates")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Helper function to get current user from token
async def get_current_user_from_token(token: str = Depends(oauth2_scheme), db=Depends(get_db)):
    return await get_current_user(token=token, db=db)

# API Routes

@app.get("/", tags=["UI"])
async def get():
    """Serve the index.html template."""
    with open("templates/index.html", "r") as file:
        html_content = file.read()
    return HTMLResponse(html_content)

# Authentication endpoints
@app.post("/register", response_model=UserDto, tags=["Authentication"])
async def register_user_endpoint(user_data: CreateUserDto, db=Depends(get_db)):
    """Register a new user."""
    return register_user(user_data, db)

@app.post("/login", tags=["Authentication"])
async def login_for_access_token(login_data: LoginDto, db=Depends(get_db)):
    """Login a user and return an access token."""
    return await login_user(login_data, db)

# WebSocket endpoint
@app.websocket("/chat/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    conversation_id: str,
    token: str = Query(..., description="JWT token for authentication")
):
    """WebSocket endpoint for chat functionality."""
    await handle_websocket_chat(websocket, conversation_id, token)

# Conversation endpoints
@app.post("/conversations", response_model=ConversationDto, tags=["Conversations"])
async def create_conversation_endpoint(
    conversation_data: CreateConversationDto,
    current_user=Depends(get_current_user_from_token),
    db=Depends(get_db)
):
    """Create a new conversation."""
    return await conversation_service.create_conversation(
        conversation_data, 
        current_user.username, 
        db
    )

@app.get("/conversations", response_model=List[ConversationDto], tags=["Conversations"])
async def get_user_conversations_endpoint(
    current_user=Depends(get_current_user_from_token),
    db=Depends(get_db)
):
    """Get conversations for the current user."""
    return await conversation_service.get_user_conversations(
        current_user.username, 
        db
    )

@app.get("/conversations/{conversation_id}", response_model=ConversationDto, tags=["Conversations"])
async def get_conversation_endpoint(
    conversation_id: str = Path(..., description="The ID of the conversation"),
    current_user=Depends(get_current_user_from_token),
    db=Depends(get_db)
):
    """Get a conversation by ID."""
    return await conversation_service.get_conversation(
        conversation_id, 
        current_user.username, 
        db
    )

@app.post("/conversations/join", response_model=ConversationDto, tags=["Conversations"])
async def join_conversation_endpoint(
    join_data: JoinConversationDto,
    current_user=Depends(get_current_user_from_token),
    db=Depends(get_db)
):
    """Join a conversation."""
    return await conversation_service.join_conversation(
        join_data, 
        current_user.username, 
        db
    )

@app.post("/conversations/leave", response_model=ConversationDto, tags=["Conversations"])
async def leave_conversation_endpoint(
    leave_data: LeaveConversationDto,
    current_user=Depends(get_current_user_from_token),
    db=Depends(get_db)
):
    """Leave a conversation."""
    return await conversation_service.leave_conversation(
        leave_data, 
        current_user.username, 
        db
    )

# Message endpoints
@app.get("/conversations/{conversation_id}/messages", response_model=List[MessageDto], tags=["Messages"])
async def get_conversation_messages_endpoint(
    conversation_id: str = Path(..., description="The ID of the conversation"),
    limit: int = Query(50, description="The maximum number of messages to return"),
    offset: int = Query(0, description="The number of messages to skip"),
    current_user=Depends(get_current_user_from_token),
    db=Depends(get_db)
):
    """Get messages for a conversation."""
    return await conversation_service.get_conversation_messages(
        conversation_id, 
        current_user.username, 
        limit, 
        offset, 
        db
    )

@app.post("/conversations/{conversation_id}/messages", response_model=MessageDto, tags=["Messages"])
async def send_message_endpoint(
    message_data: SendMessageDto,
    conversation_id: str = Path(..., description="The ID of the conversation"),
    current_user=Depends(get_current_user_from_token),
    db=Depends(get_db)
):
    """Send a message to a conversation."""
    # Ensure conversation IDs match
    if message_data.conversation_id != conversation_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conversation ID in path must match conversation ID in message data"
        )
    
    # First save the message
    message = await conversation_service.send_message(
        message_data, 
        current_user.username, 
        db
    )
    
    # Then process with agency asynchronously 
    # This will return the agency's response
    agency_response = await agency_service.process_message_with_agency(
        message_data,
        current_user.username,
        db
    )
    
    # Return the agency's response
    return agency_response

@app.get("/conversations/{conversation_id}/state", response_model=ConversationStateDto, tags=["Conversations"])
async def get_conversation_state_endpoint(
    conversation_id: str = Path(..., description="The ID of the conversation"),
    current_user=Depends(get_current_user_from_token),
    db=Depends(get_db)
):
    """Get the current state of a conversation, including active users and recent messages."""
    return await conversation_service.get_conversation_state(
        conversation_id, 
        current_user.username, 
        db
    )

if __name__ == "__main__":
    print("Starting FastAPI server...")
    print("Ensure .env file has OPENAI_API_KEY and SECRET_KEY")
    print("Access the chat interface at http://localhost:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 