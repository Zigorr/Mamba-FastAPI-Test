import uvicorn # type: ignore
from fastapi import FastAPI, Depends, HTTPException, status, Query, Request, Response # type: ignore
from fastapi.responses import HTMLResponse # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
import os
from dotenv import load_dotenv # type: ignore
import logging
from typing import Dict
import certifi # type: ignore
from sqlalchemy.orm import Session # type: ignore
from passlib.context import CryptContext # type: ignore
from datetime import datetime
from reset_database import reset_database

# State and Auth
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
from database import (
    get_db, engine, SessionLocal, 
    # Rename imports for clarity
    create_valkey_pool as startup_create_pool, 
    close_valkey_pool as shutdown_close_pool, 
    get_valkey_connection 
)
from models import Base, User
from repositories import ConversationRepository, MessageRepository, UserRepository
from services.agency_services import AgencyService
from utils.valkey_utils import publish_message_to_valkey
import json

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
    allow_origins=["http://localhost:5173","http://localhost:8000", "http://178.128.90.137", "https://front-genta.xyz", "http://front-genta.xyz"],  # Or restrict to your frontend URL like ["https://yourfrontend.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables
Base.metadata.create_all(bind=engine)

# @app.options("/{path:path}")
# async def preflight(full_path: str, request: Request) -> Response:
#     return Response(status_code=204)


@app.get("/")
async def read_root():
     return {"message": "Welcome to the Mamba FastAPI"}

@app.post("/register", response_model=UserDto, tags=["Authentication"])
async def register_user_endpoint(user_data: CreateUserDto, db=Depends(get_db)):
    """Register a new user."""
    return register_user(user_data, db)

@app.post("/login", tags=["Authentication"])
async def login_for_access_token(login_data: LoginDto, db=Depends(get_db)):
    """Login a user and return an access token."""
    return await login_user(login_data, db)

@app.get("/verify-email", tags=["Authentication"], response_class=HTMLResponse)
async def verify_email_endpoint(token: str = Query(...), db: Session = Depends(get_db)):
    """Verify user's email address using the provided token."""
    user_repo = UserRepository(db)
    # Use the correct method name from UserRepository
    user = user_repo.get_by_verification_token(token)

    if not user:
        return HTMLResponse(content="<h1>Invalid or expired verification token.</h1>", status_code=400)

    if user.is_verified:
        # Optionally redirect to login or dashboard
        return HTMLResponse(content="<h1>Email already verified. You can now log in.</h1>")

    # Use the correct method name from UserRepository
    if user_repo.verify_user(token):
        logger.info(f"Email verified successfully for user {user.email}")
        # Optionally redirect to a login page or show a success message
        return HTMLResponse(content="<h1>Email verified successfully! You can now log in.</h1>")
    else:
        # This case should ideally not happen if get_by_verification_token worked
        logger.error(f"Verification failed unexpectedly for token {token}")
        return HTMLResponse(content="<h1>Email verification failed. Please try again or contact support.</h1>", status_code=500)

@app.post("/chat", tags=["Chat"])
async def create_chat(
    request: dict,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} authenticated for new conversation")
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

    # Create new conversation
    conversation_repo = ConversationRepository(db)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conversation = conversation_repo.create_from_dto(
        CreateConversationDto(name=f"Chat @{timestamp}"),
        creator_email=current_user.email
    )

    logger.info(f"Created new conversation {conversation.id} for user {current_user.email}")

    # Forward the message to the chat endpoint
    response = await chat_endpoint(
        conversation_id=conversation.id,
        request=request,
        token=token,
        db=db
    )
    response["conversation_id"] = conversation.id
    response["conversation_name"] = conversation.name
    return response

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
        logger.info(f"User {current_user.email} authenticated")
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

    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)  # Create message repository

    # Validate that the conversation belongs to the current user
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if conversation.user_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation"
        )

    logger.info(f"Received message from client {current_user.email} for conversation {conversation_id}: {message}")

    # Save user message to database
    user_message_dto = SendMessageDto(
        conversation_id=conversation_id,
        content=message
    )
    message_repo.create_from_dto(user_message_dto, current_user.email, is_from_agency=False)

    # Initialize or load agency
    agency = AgencyService.initialize_agency(conversation_id, conversation_repo)

    try:
        # Get completion from agency
        agency_response = agency.get_completion(message=message)
        
        
        # Save AI response to database
        ai_message_dto = SendMessageDto(
            conversation_id=conversation_id,
            content=agency_response
        )
        message_repo.create_from_dto(ai_message_dto, None, is_from_agency=True)
        
        agency_action = agency.shared_state.get("action")
        if agency_action:
            response = {
                "response": agency_response, 
                "is_from_agency": True, 
                "action": agency_action
            }
        else:
            response = {
                "response": agency_response, "is_from_agency": True}
            
        if agency_action and agency_action.get("action-type") == "keywords_ready":
            agency.shared_state.set("action", None)
        # Save updated state
        conversation_repo.save_shared_state(conversation_id, agency.shared_state.data)

        # --- Publish to Valkey AFTER successful commit ---
        try:
            if user_message_dto:
                await publish_message_to_valkey(conversation_id, message_repo.to_dto(user_message_dto))
            if ai_message_dto:
                await publish_message_to_valkey(conversation_id, message_repo.to_dto(ai_message_dto))
            
            return response
        except Exception as pub_e:
            # Log failure to publish but don't fail the request, DB is source of truth
            logger.error(f"Failed to publish message(s) to Valkey for conv {conversation_id}: {pub_e}")
            return response
    except Exception as e:
        logger.error(f"Error processing message for {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {str(e)}"
        )

@app.get("/messages/{conversation_id}", tags=["Chat"])
async def get_messages_flexible(
    conversation_id: str,
    limit: int = Query(0, description="Maximum number of messages to retrieve, set to 0 for all messages"),
    offset: int = Query(0, description="Number of messages to skip"),
    order: str = Query("desc", description="Order of messages: 'asc' for oldest first, 'desc' for newest first"),
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """
    Get messages for a conversation with flexible options for ordering and pagination.
    - Use order='asc' to get messages in chronological order (oldest first)
    - Use order='desc' to get messages in reverse chronological order (newest first)
    - Set limit=0 to get all messages (no limit)
    - Use offset to skip messages for pagination
    """
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} accessing messages for conversation {conversation_id}")
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )

    # Validate conversation exists and belongs to user
    conversation_repo = ConversationRepository(db)
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if conversation.user_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation"
        )
    
    # Use custom repository method for flexible retrieval
    message_repo = MessageRepository(db)
    
    # Validate order parameter
    if order.lower() not in ["asc", "desc"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must be 'asc' or 'desc'"
        )
    
    # Get messages with the specified options
    messages = message_repo.get_messages_flexible(
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
        ascending=(order.lower() == "asc")
    )
    
    # Convert to DTOs
    message_dtos = [message_repo.to_dto(message) for message in messages]

    agency = AgencyService.initialize_agency(conversation_id, conversation_repo)

    latest_action = agency.shared_state.get("action", None)

    keyword_tables = agency.shared_state.get("keywords_output", None)
    generated_content = {}
    
    if keyword_tables:
        generated_content["keyword_tables"] = keyword_tables
    
    return {
        "messages": message_dtos, 
        "conversation_id": conversation_id,
        "total_count": message_repo.count_for_conversation(conversation_id),
        "order": order,
        "limit": limit,
        "offset": offset,
        "generated_content": generated_content,
        "action": latest_action
    }

@app.get("/conversations", tags=["Chat"])
async def get_user_conversations(
    limit: int = Query(20, description="Maximum number of conversations to retrieve"),
    offset: int = Query(0, description="Number of conversations to skip"),
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Get all conversations for the current user with their latest messages."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} retrieving conversations")
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )
    
    # Get conversations for user
    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)
    
    conversations = conversation_repo.get_for_user(current_user.email, limit, offset)
    result = []
    
    # For each conversation, get the latest message
    for conversation in conversations:
        conv_dto = conversation_repo.to_dto(conversation)
        latest_messages = message_repo.get_for_conversation(conversation.id, limit=1, offset=0)
        
        # Add latest message preview if available
        if latest_messages:
            latest_message = message_repo.to_dto(latest_messages[0])
            conv_dto.latest_message = latest_message
        
        result.append(conv_dto)
    
    return {"conversations": result}

@app.post("/submit_form/{conversation_id}", tags=["Chat"])
async def submit_form(
    conversation_id: str,
    request: dict,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Submit a form for a conversation."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} authenticated")
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )

    # Get message from request
    form_data = request.get("form_data")
    form_action = request.get("action", None)
    if not form_data:
        if form_action == "cancel_form":
            message = "I have cancelled the form"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Form data is required"
            )

    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)  # Create message repository

    # Validate that the conversation belongs to the current user
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if conversation.user_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation"
        )

    logger.info(f"Received business form data from client {current_user.email} for conversation {conversation_id}")
    message = "I have submitted the form"
    # Save user message to database
    user_message_dto = SendMessageDto(
        conversation_id=conversation_id,
        content=message
    )
    message_repo.create_from_dto(user_message_dto, current_user.email, is_from_agency=False)

    # Initialize or load agency
    agency = AgencyService.initialize_agency(conversation_id, conversation_repo)

    try:
        # Set the form data in the shared state
        if form_data:
            agency.shared_state.set('business_info_data', form_data)
        if form_action == "cancel_form":
            agency.shared_state.set('action', None)
        # Get completion from agency
        agency_response = agency.get_completion(message=message)
        
        # Save updated state
        conversation_repo.save_shared_state(conversation_id, agency.shared_state.data)
        
        # Save AI response to database
        ai_message_dto = SendMessageDto(
            conversation_id=conversation_id,
            content=agency_response
        )
        message_repo.create_from_dto(ai_message_dto, None, is_from_agency=True)
        
        if agency.shared_state.get("action"):
            action = agency.shared_state.get("action")
            return {"response": agency_response, "is_from_agency": True, "action": action}
        else:
            return {"response": agency_response, "is_from_agency": True}
    except Exception as e:
        logger.error(f"Error processing message for {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {str(e)}"
        )

    # --- Update any other publishing calls similarly (e.g., in /submit_form) ---

@app.post("/get_keywords/{conversation_id}", tags=["Chat"])
async def get_keywords(
    conversation_id: str,
    request: dict,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} authenticated")
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )

    # Get message from request
    table_id = request.get("table_id")
    if not table_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Table ID is required"
        )

    conversation_repo = ConversationRepository(db)

    # Validate that the conversation belongs to the current user
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if conversation.user_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation"
        )

    logger.info(f"Received business form data from client {current_user.email} for conversation {conversation_id}")

    agency = AgencyService.initialize_agency(conversation_id, conversation_repo)
    keywords_output = agency.shared_state.get('keywords_output')
    table_data = keywords_output.get(table_id)
    if not table_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table ID not found"
        )
    agency.shared_state.set('action', None)
    conversation_repo.save_shared_state(conversation_id, agency.shared_state.data)

    return table_data

@app.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Chat"])
async def delete_conversation_endpoint(
    conversation_id: str,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Deletes an entire conversation and its messages."""
    # 1. Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} attempting to delete conversation {conversation_id}")
    except HTTPException as e:
        # Re-raise authentication errors
        raise e 

    conversation_repo = ConversationRepository(db)
    
    # 2. Find the conversation
    # Use the standard get, no lock needed for deletion check
    conversation = conversation_repo.get_by_id(conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    # 3. Authorization Check: Ensure the current user owns the conversation
    if conversation.user_email != current_user.email:
        logger.warning(f"User {current_user.email} forbidden to delete conversation {conversation_id} owned by {conversation.user_email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this conversation"
        )

    # 4. Perform Deletion
    try:
        deleted = conversation_repo.delete_conversation(conversation_id)
        if deleted:
            logger.info(f"Conversation {conversation_id} deleted successfully by user {current_user.email}")
            # Return No Content (204) on success, FastAPI handles this automatically by returning None
            return None 
        else:
            # This case should ideally not be reached if the conversation was found above
            logger.error(f"Conversation {conversation_id} found but deletion failed.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete conversation")
            
    except Exception as e:
        # Catch potential DB errors during delete
        logger.error(f"Error deleting conversation {conversation_id}: {e}", exc_info=True)
        # Consider rolling back if delete_conversation didn't commit, though it does now.
        # db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not delete conversation: {e}")

# Add startup/shutdown events
@app.on_event("startup")
async def startup_event():
    logger.info("Application startup...")
    logger.info("Creating Valkey connection pool...") # Update log message
    await startup_create_pool() # Call renamed function
    # Add other startup tasks if needed

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown...")
    logger.info("Closing Valkey connection pool...") # Update log message
    await shutdown_close_pool() # Call renamed function
    # Add other shutdown tasks if needed

if __name__ == "__main__":
    print("Starting FastAPI server...")
    print("Ensure .env file has OPENAI_API_KEY and SECRET_KEY")
    print("Access the chat interface at http://localhost:8000")
    
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
