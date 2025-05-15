import uvicorn # type: ignore
import os # Ensure os is imported early
# from dotenv import load_dotenv # type: ignore # No longer needed here
from core.config import settings # Import settings early to load .env
from contextlib import asynccontextmanager # Import for lifespan manager
import uuid # Added for correlation ID
from urllib.parse import urlencode # Added for Google OAuth callback

# --- Load Environment Variables --- 
# load_dotenv(override=True) # Moved to the top and handled by core.config
# --------------------------------

from fastapi import FastAPI, Depends, HTTPException, status, Query, Request, Response # type: ignore
from fastapi.responses import HTMLResponse, RedirectResponse # type: ignore # Added RedirectResponse
from fastapi.middleware.cors import CORSMiddleware # type: ignore
import logging
from typing import Dict, Any, List, Optional # Ensure List and Optional are imported
import certifi # Ensure certifi is imported before use
from sqlalchemy.orm import Session # type: ignore
from passlib.context import CryptContext # type: ignore
from datetime import datetime, timedelta, timezone
from reset_database import reset_database
from reset_pins import reset_all_pins

# State and Auth
import auth
from auth import get_current_user, create_access_token, get_token_header, verify_google_id_token, verify_token
from services.user_services import register_user, login_user, rename_conversation, delete_conversation, get_conversation_details, get_user_conversations, toggle_conversation_pin, get_or_create_google_user
from dto import (
    CreateUserDto, UserDto, LoginDto, 
    ConversationDto, CreateConversationDto,
    MessageDto, SendMessageDto, ConversationStateDto,
    UpdateConversationStateDto, RenameConversationDto,
    ProjectDto, CreateProjectDto, UpdateProjectDataDto,
    UpdateProjectDto, UpdateProjectSpecificDto,
    GoogleOAuthRevokeRequest # Added for revoke endpoint
)
from pydantic import BaseModel, Field # Add Field

# Database and Models
from database import (
    get_db, engine, SessionLocal, 
    # Rename imports for clarity
    create_valkey_pool, # Make sure this is imported
    close_valkey_pool,  # Make sure this is imported
    get_valkey_connection 
)
from models import Base, User as UserModel # Alias User to UserModel
from models import GoogleService as GoogleServiceModel # Added
from repositories import ConversationRepository, MessageRepository, UserRepository, ProjectRepository
from services.agency_services import AgencyService
from services.project_services import extract_project_data, generate_project_data, delete_project_and_data, update_project_specific_fields
from services.google_oauth_service import GoogleOAuthService # Added
from services.search_console_service import SearchConsoleService # Added
from services.analytics_service import AnalyticsService # Added
# from utils.valkey_utils import publish_message_to_valkey
import json

# os.environ["SSL_CERT_FILE"] = certifi.where() # Set via settings if needed or ensure certifi is available
if settings.SSL_CERT_FILE:
    os.environ["SSL_CERT_FILE"] = settings.SSL_CERT_FILE
elif certifi.where(): # Default to certifi.where() if not in settings
    os.environ["SSL_CERT_FILE"] = certifi.where()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Lifespan manager for startup and shutdown events
@asynccontextmanager
async def lifespan(app_instance: FastAPI): # Changed 'app' to 'app_instance' to avoid conflict if app is defined globally later
    # Startup logic
    logger.info("Application startup (lifespan)... Genta was here")
    logger.info("Creating Valkey/Redis connection pool (lifespan)... Genta was here")
    await create_valkey_pool()
    # Add other startup tasks if needed
    yield
    # Shutdown logic
    logger.info("Application shutdown (lifespan)... Genta was here")
    logger.info("Closing Valkey/Redis connection pool (lifespan)... Genta was here")
    await close_valkey_pool()
    # Add other shutdown tasks if needed

app = FastAPI(
    title="Mamba FastAPI Chat",
    description="A FastAPI application with WebSocket chat and user authentication",
    version="1.0.0",
    openapi_tags=[
        {
            "name": "Authentication",
            "description": "Operations related to user authentication"
        },
        {
            "name": "Chat",
            "description": "Chat operations, conversations and messages"
        },
        {
            "name": "Admin",
            "description": "Administrative operations"
        },
        {
            "name": "Projects",
            "description": "Operations related to projects"
        },
        {
            "name": "Google OAuth",
            "description": "Operations related to Google OAuth"
        },
        {
            "name": "Google Search Console",
            "description": "Operations for Google Search Console"
        },
        {
            "name": "Google Analytics 4",
            "description": "Operations for Google Analytics 4"
        }
    ],
    lifespan=lifespan # Add the lifespan manager here
)

# --- CORS Middleware --- 
# Ensure this is placed before any routers if you have them, 
# and generally early in the middleware stack.
origins = [
    settings.FRONTEND_URL,  # From your .env file via core/config.py
    "https://front-genta.xyz", # The specific frontend URL you provided
    # You can add other origins if needed, e.g., for local development if different
    # "http://localhost:3000", 
    # "http://127.0.0.1:3000",
]

# Add trailing slashes to origins if they don't have them, or ensure consistency
# as some browsers/servers are picky.
# For simplicity, FastAPI/Starlette are generally flexible.

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # Important for cookies, authorization headers
    allow_methods=["*"],    # Allows all standard methods
    allow_headers=["*"],    # Allows all headers
)
# --- End CORS Middleware ---

# Correlation ID Middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    # Check for incoming header, otherwise generate a new one
    correlation_id = request.headers.get("X-Correlation-ID")
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
    
    # Store it in request.state to make it accessible in path operations
    request.state.correlation_id = correlation_id
    
    # Call the next middleware or path operation
    response = await call_next(request)
    
    # Add it to the response headers
    response.headers["X-Correlation-ID"] = correlation_id
    
    return response

# Cache TTLs
MESSAGES_CACHE_TTL_SECONDS = 60  # 1 minute
# CONVERSATION_DETAILS_CACHE_TTL_SECONDS = 300 # Defined in user_services.py
# USER_CONVERSATIONS_CACHE_TTL_SECONDS = 120 # Defined in user_services.py

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Create database tables
Base.metadata.create_all(bind=engine)

# Removed get_user_service function

# @app.options("/{path:path}")
# async def preflight(full_path: str, request: Request) -> Response:
#     return Response(status_code=204)


@app.get("/")
async def read_root():
     return {"message": "Welcome to Mamba FastAPI Server"}

class GoogleLoginRequest(BaseModel):
    token: str # This will be the Google ID token from the frontend

@app.post("/register", response_model=UserDto, tags=["Authentication"])
async def register_user_endpoint(user_data: CreateUserDto, db: Session = Depends(get_db)):
    """Register a new user."""
    return register_user(user_data, db)

@app.post("/login", tags=["Authentication"])
async def login_for_access_token(login_data: LoginDto, db=Depends(get_db)):
    """Login a user and return an access token."""
    return await login_user(login_data, db)

@app.post("/subscribe", tags=["User"])
async def subscribe_user_endpoint(db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    """Allows an authenticated user to 'subscribe'."""

    if current_user.email.endswith("@mamba.agency"):
        # Mamba agency users already have unlimited access
        return {"message": "Mamba agency users have unlimited access by default."}

    if current_user.is_subscribed:
        return {"message": "You are already subscribed and have unlimited tokens."}

    current_user.is_subscribed = True
    current_user.token_limit = None  # Unlimited tokens upon subscription
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    # Placeholder for actual subscription benefits/UI update
    return {"message": "Thanks for the support! Follow development to see the updates! You now have unlimited tokens."}


@app.post("/project-data", tags=["Projects"])
async def create_project_data(
    request: dict,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Create project data for a project.
    
    This endpoint accepts two formats:
    1. URL format: {"project_url": "https://example.com"}
    2. Direct format: {
        "project_name": "Company Name",
        "products_description": "Description of products",
        "personas_description": "Description of target personas",
        "competitors_description": "Description of competitors"
    }
    """
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} authenticated for project data extraction")
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )
    
    # Check which format is being provided
    if request.get("project_url"):
        # URL-based format
        project_url = request.get("project_url")
        logger.info(f"Processing URL-based project data extraction: {project_url}")
        try:
            return extract_project_data(project_url)
        except Exception as e:
            logger.error(f"Error extracting project data: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error extracting project data: {e}"
            );
    elif all(k in request for k in ["project_name", "products_description", "personas_description", "competitors_description"]):
        # Direct description-based format
        project_name = request.get("project_name")
        products_description = request.get("products_description")
        personas_description = request.get("personas_description")
        competitors_description = request.get("competitors_description")
        
        logger.info(f"Processing description-based project data generation for: {project_name}")
        try:
            return generate_project_data(
                project_name=project_name,
                products_description=products_description,
                personas_description=personas_description,
                competitors_description=competitors_description
            )
        except Exception as e:
            logger.error(f"Error generating project data: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error generating project data: {e}"
            );
    else:
        # Neither format provided correctly
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'project_url' OR all of ('project_name', 'products_description', 'personas_description', 'competitors_description') must be provided"
        )

@app.post("/projects", response_model=ProjectDto, tags=["Projects"])
async def create_project_endpoint(
    project_data: CreateProjectDto, 
    token: str = Depends(get_token_header), 
    db: Session = Depends(get_db)
    # user_service: UserManagementService = Depends(get_user_service) # Removed
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials for project creation",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = auth.verify_token(token, credentials_exception) # Use auth.verify_token
    user_email = payload.get("email") # Changed from "sub" to "email" based on auth.verify_token
    if not user_email:
        raise credentials_exception # Should be caught by verify_token if email is None

    project_repo = ProjectRepository(db)
    
    # Check for existing project with the same name for the user
    existing_project = project_repo.get_by_name_and_user(project_data.name, user_email)
    if existing_project:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project with name '{project_data.name}' already exists for this user."
        )
        
    new_project_model = project_repo.create_from_dto(project_data, user_email)
    return project_repo.to_dto(new_project_model)

@app.get("/projects", response_model=List[ProjectDto], tags=["Projects"])
async def get_user_projects_endpoint(
    token: str = Depends(get_token_header), 
    db: Session = Depends(get_db)
    # user_service: UserManagementService = Depends(get_user_service) # Removed
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials for fetching projects",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = auth.verify_token(token, credentials_exception) # Use auth.verify_token
    user_email = payload.get("email") # Changed from "sub" to "email"
    if not user_email:
        raise credentials_exception
    
    project_repo = ProjectRepository(db)
    projects = project_repo.get_by_user_email(user_email)
    return [project_repo.to_dto(p) for p in projects]

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

    # Get project_id from request (if provided)
    project_id = request.get("project_id")
    
    # If project_id is provided, verify it exists and belongs to the user
    if project_id:
        project_repo = ProjectRepository(db)
        project = project_repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        if project.user_email != current_user.email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this project"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project ID is required"
        )
    # Create new conversation
    conversation_repo = ConversationRepository(db)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conversation_dto = CreateConversationDto(
        name=f"Chat @{timestamp}", 
        project_id=project_id
    )
    conversation = conversation_repo.create_from_dto(
        conversation_dto,
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

        # Token Management Logic
        is_mamba_user = current_user.email.endswith("@mamba.agency")
        is_subscribed_user = current_user.is_subscribed
        can_have_unlimited_tokens = is_mamba_user or is_subscribed_user

        if not can_have_unlimited_tokens:
            now = datetime.now(timezone.utc)
            needs_token_reset = False
            if current_user.tokens_last_reset_at is None:
                needs_token_reset = True
            elif now - current_user.tokens_last_reset_at > timedelta(hours=24):
                needs_token_reset = True

            if needs_token_reset:
                current_user.token_limit = settings.DEFAULT_FREE_USER_TOKEN_LIMIT
                current_user.tokens_last_reset_at = now
                db.add(current_user)
                db.commit()
                db.refresh(current_user)
            
            if current_user.token_limit is None or current_user.token_limit <= 0:
                logger.warning(f"User {current_user.email} token limit {current_user.token_limit} insufficient.")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Token limit reached. Please subscribe for unlimited access or wait 24 hours for tokens to reset."
                )
        # End of Token Management Logic

    except HTTPException as e:
        raise e

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
        
        # Decrement token for free users if operation was successful
        if not can_have_unlimited_tokens:
            if current_user.token_limit is not None and current_user.token_limit > 0:
                current_user.token_limit -= 1 # Assuming 1 token per message
                db.add(current_user)
                db.commit()
            # else: log or handle case where token_limit became <=0 unexpectedly after check? 
            # For now, the check before agency.get_completion should prevent this.

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
        # try:
        #     if user_message_dto:
        #         await publish_message_to_valkey(conversation_id, message_repo.to_dto(user_message_dto))
        #     if ai_message_dto:
        #         await publish_message_to_valkey(conversation_id, message_repo.to_dto(ai_message_dto))
            
        #     return response
        # except Exception as pub_e:
        #     # Log failure to publish but don't fail the request, DB is source of truth
        #     logger.error(f"Failed to publish message(s) to Valkey for conv {conversation_id}: {pub_e}")
        #     return response
        return response # Return original response directly
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
    Implements cache-aside (lazy loading) pattern with Redis.
    """
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        # logger.info(f"User {current_user.email} accessing messages for conversation {conversation_id}") # Moved logging after cache check
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )

    redis_conn = await get_valkey_connection()
    # Create a cache key that includes all query parameters that affect the result
    cache_key = f"messages:{conversation_id}:limit_{limit}:offset_{offset}:order_{order.lower()}"

    if redis_conn:
        try:
            cached_data_json = await redis_conn.get(cache_key)
            if cached_data_json:
                logger.info(f"Cache HIT for messages: {cache_key} by user {current_user.email}")
                return json.loads(cached_data_json)
            else:
                logger.info(f"Cache MISS for messages: {cache_key} by user {current_user.email}")
        except Exception as e:
            logger.error(f"Redis GET error for messages {cache_key}: {e}", exc_info=True)
            # Proceed to fetch from DB if Redis fails

    logger.info(f"User {current_user.email} accessing messages for conversation {conversation_id} from DB (after cache miss/error)")

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
async def get_conversations_with_messages(
    limit: int = Query(20, description="Maximum number of conversations to retrieve"),
    offset: int = Query(0, description="Number of conversations to skip"),
    project_id: str = Query(None, description="Filter conversations by project ID"),
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
    
    # If project_id is provided, verify it exists and belongs to the user
    if project_id:
        project_repo = ProjectRepository(db)
        project = project_repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        if project.user_email != current_user.email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this project"
            )
    
    # Get conversations for user
    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)
    
    conversations = conversation_repo.get_for_user(
        email=current_user.email, 
        limit=limit, 
        offset=offset,
        project_id=project_id
    )
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

@app.post("/conversations/{conversation_id}/toggle-pin", response_model=ConversationDto, tags=["Chat"])
async def toggle_pin_endpoint(
    conversation_id: str,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Toggle the pinned status of a conversation."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} attempting to toggle pin for conversation {conversation_id}")
    except HTTPException as e:
        raise e

    # Call the service function
    return await toggle_conversation_pin(conversation_id, current_user.email, db)

@app.get("/conversations/{conversation_id}", tags=["Chat"])
async def get_conversation_details_endpoint(
    conversation_id: str,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific conversation."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} requesting details for conversation {conversation_id}")
    except HTTPException as e:
        raise e

    # Call the service function
    return await get_conversation_details(conversation_id, current_user.email, db)

@app.get("/user/conversations", tags=["Chat"])
async def get_user_conversations_endpoint(
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Get all conversations belonging to the authenticated user with essential details."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} requesting their conversations")
    except HTTPException as e:
        raise e

    # Call the service function with the user's email and database session
    return await get_user_conversations(current_user.email, db)

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
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} attempting to delete conversation {conversation_id}")
    except HTTPException as e:
        # Re-raise authentication errors
        raise e 

    # Call the service function
    return await delete_conversation(conversation_id, current_user.email, db)

@app.patch("/conversations/{conversation_id}/rename", response_model=ConversationDto, tags=["Chat"])
async def rename_conversation_endpoint(
    conversation_id: str,
    rename_data: RenameConversationDto,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Rename an existing conversation."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} attempting to rename conversation {conversation_id}")
    except HTTPException as e:
        raise e

    # Call the service function
    return await rename_conversation(conversation_id, rename_data.name, current_user.email, db)

@app.post("/auth/google", tags=["Authentication"])
async def google_auth_endpoint(request: GoogleLoginRequest, db: Session = Depends(get_db)):
    """Handles Google Sign-In/Sign-Up."""
    google_token = request.token
    try:
        idinfo = await verify_google_id_token(google_token, settings.GOOGLE_CLIENT_ID)
        if not idinfo or "email" not in idinfo:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")

        email = idinfo["email"]
        first_name = idinfo.get("given_name", "")
        last_name = idinfo.get("family_name", "")

        auth_response = await get_or_create_google_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            db=db
        )
        return auth_response

    except ValueError as e: # Specific exception from google-auth library for invalid token
        logger.error(f"Google token verification failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google token: {e}")
    except HTTPException as e:
        raise e # Re-raise existing HTTPExceptions
    except Exception as e:
        logger.error(f"Error during Google authentication for token {google_token[:20]}...: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google authentication failed.")

@app.get("/projects/{project_id}", response_model=ProjectDto, tags=["Projects"])
async def get_project_details_endpoint(
    project_id: str, 
    token: str = Depends(get_token_header), 
    db: Session = Depends(get_db)
    # user_service: UserManagementService = Depends(get_user_service) # Removed
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials for project details",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = auth.verify_token(token, credentials_exception) # Use auth.verify_token
    user_email = payload.get("email") # Changed from "sub" to "email"
    if not user_email:
        raise credentials_exception

    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_email != user_email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not authorized to access this project")
    return project_repo.to_dto(project)

@app.patch("/projects/{project_id}", response_model=ProjectDto, tags=["Projects"])
async def update_project_details_endpoint(
    project_id: str,
    update_data: UpdateProjectSpecificDto, # Use the new DTO
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
    # user_service: UserManagementService = Depends(get_user_service) # Removed
):
    """Update specific details of a project (name, target_market, products, personas, competitors)."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials for updating project",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Verify token first using auth.verify_token to get email efficiently
        payload = auth.verify_token(token, credentials_exception)
        user_email = payload.get("email")
        if not user_email:
            raise credentials_exception
        logger.info(f"User {user_email} attempting to update project {project_id}")
    except HTTPException as e:
        raise credentials_exception

    # Call the specific update service function
    try:
        updated_project_dto = await update_project_specific_fields(
            project_id=project_id,
            user_email=user_email,
            update_data=update_data,
            db=db
        )
        return updated_project_dto
    except HTTPException as e:
        # Re-raise HTTP exceptions from the service layer (e.g., 404, 403, 500)
        raise e
    except Exception as e:
        # Catch any unexpected errors from the service layer
        logger.error(f"Unexpected error calling update_project_specific_fields for project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while updating the project."
        )

@app.get("/projects/{project_id}/conversations", tags=["Projects"])
async def get_conversations_for_project(
    project_id: str,
    limit: int = Query(20, description="Maximum number of conversations to retrieve"),
    offset: int = Query(0, description="Number of conversations to skip"),
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Get conversations for a specific project."""
    try:
        current_user = await get_current_user(token=token, db=db)
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )
    
    # Verify project exists and belongs to user
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    if project.user_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this project"
        )
    
    # Get conversations for project
    conversation_repo = ConversationRepository(db)
    conversations = conversation_repo.get_for_project(
        project_id=project_id,
        limit=limit,
        offset=offset
    )
    
    # Return conversation name, ID, is_pinned, and updated_at
    result = [{
        "id": conv.id, 
        "name": conv.name, 
        "is_pinned": conv.is_pinned,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None
    } for conv in conversations]
    
    return {"conversations": result}

@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Projects"])
async def delete_project_endpoint(
    project_id: str,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Deletes a project and all its associated data (conversations, messages)."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials for deleting project",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} attempting to delete project {project_id}")
    except HTTPException as e:
        raise credentials_exception # Use the more specific exception

    if not current_user: # Should be caught by get_current_user, but safeguard
        raise credentials_exception

    # Call the service function to handle deletion (this needs implementation)
    try:
        # Assume delete_project_and_data verifies ownership internally or we do it here first
        # For consistency, let's verify ownership here before calling the service
        project_repo = ProjectRepository(db)
        project = project_repo.get_by_id(project_id)

        if not project:
            # Idempotency: If not found, treat as success (already deleted)
            logger.info(f"Project {project_id} not found for deletion by user {current_user.email}. Assuming already deleted.")
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        if project.user_email != current_user.email:
            logger.warning(f"User {current_user.email} attempted to delete project {project_id} owned by {project.user_email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this project"
            )

        # Call the service function to perform the deletion
        await delete_project_and_data(project_id=project_id, user_email=current_user.email, db=db) # Pass necessary info

        logger.info(f"Project {project_id} and associated data successfully deleted by user {current_user.email}")
        # Return 204 No Content on successful deletion
        return Response("deleted successfully", status_code=status.HTTP_200_OK)

    except HTTPException as e:
        # Re-raise HTTP exceptions from the service or ownership check
        raise e
    except Exception as e:
        # Log unexpected errors during deletion
        logger.error(f"Error deleting project {project_id} for user {current_user.email}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while trying to delete the project."
        )

@app.get("/api/google/oauth/authorize", tags=["Google OAuth"])
async def google_oauth_authorize(
    product: str, # "search_console" or "ga4"
    request: Request, 
    db: Session = Depends(get_db),
    valkey_conn = Depends(get_valkey_connection),
    token: str = Depends(get_token_header) 
):
    """
    Initiates the Google OAuth2 flow for the specified product.
    Returns the Google authorization URL for the frontend to redirect to.
    """
    try:
        current_user: UserModel = await get_current_user(token=token, db=db)
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=f"Authentication required: {e.detail}")

    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")

    try:
        service_name_enum = GoogleServiceModel(product.lower())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid product specified. Use 'search_console' or 'ga4'.")

    oauth_service = GoogleOAuthService(db=db)
    try:
        # Use the redirect URI from settings
        authorization_url = await oauth_service.build_authorization_url(
            user_email=current_user.email,
            service_name=service_name_enum,
            valkey_conn=valkey_conn
        )
        
        # Return the URL instead of redirecting
        return {"authUrl": authorization_url}
        
    except ValueError as e: 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error building Google authorization URL: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not initiate Google OAuth flow.")


@app.get(settings.GOOGLE_OAUTH_CALLBACK_PATH, tags=["Google OAuth"])
async def google_oauth_callback(
    code: str,
    state: str,
    scope: str, 
    request: Request,
    db: Session = Depends(get_db),
    valkey_conn = Depends(get_valkey_connection)
):
    """
    Handles the callback from Google after user authorization.
    Exchanges the authorization code for tokens and stores them.
    Redirects the user to the frontend.
    """
    oauth_service = GoogleOAuthService(db=db)
    try:
        result = await oauth_service.exchange_code_for_tokens(
            code=code,
            state_key_from_google=state, 
            valkey_conn=valkey_conn
        )
        redirect_url = f"{settings.FRONTEND_URL.rstrip('/')}/settings?google_auth_status=success&service={result.get('service_name', 'unknown')}"
        return RedirectResponse(url=redirect_url)

    except HTTPException as e: 
        error_params = urlencode({"google_auth_status": "error", "detail": e.detail})
        redirect_url = f"{settings.FRONTEND_URL.rstrip('/')}/settings?{error_params}"
        return RedirectResponse(url=redirect_url) 
    except Exception as e:
        logger.error(f"Error processing Google OAuth callback: {e}", exc_info=True)
        error_params = urlencode({"google_auth_status": "error", "detail": "An internal error occurred during Google authentication."})
        redirect_url = f"{settings.FRONTEND_URL.rstrip('/')}/settings?{error_params}"
        return RedirectResponse(url=redirect_url)


# The GoogleOAuthService needs to be updated to handle the redirect_uri parameter
# Here's how the build_authorization_url method might need to be modified:

# Example modification for your GoogleOAuthService class (adjust to match your actual implementation)
async def build_authorization_url(
    self,
    user_email: str,
    service_name: GoogleServiceModel,
    redirect_uri: str,  # Add this parameter
    valkey_conn
) -> str:
    """
    Builds the Google OAuth authorization URL.
    
    Args:
        user_email: The email of the user initiating the OAuth flow
        service_name: The Google service being authorized
        redirect_uri: The callback URL after authorization
        valkey_conn: Connection to the key-value store
        
    Returns:
        The authorization URL
    """
    # Your existing code...
    
    # Use the provided redirect_uri instead of a hardcoded one
    oauth_flow = flow.Flow.from_client_secrets_file(
        settings.GOOGLE_CLIENT_SECRETS_FILE,
        scopes=self._get_scopes_for_service(service_name),
        redirect_uri=redirect_uri  # Use the passed redirect_uri
    )
    
    # Generate state token and store it
    state_token = secrets.token_urlsafe(32)
    
    # Store state token with user information
    state_data = {
        "user_email": user_email,
        "service_name": service_name.value,
        "created_at": datetime.utcnow().isoformat()
    }
    
    # Store in your key-value store
    await valkey_conn.set(f"oauth_state:{state_token}", json.dumps(state_data), ex=1800)  # 30 minute expiry
    
    # Get authorization URL with state
    authorization_url, _ = oauth_flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
        state=state_token
    )
    
    return authorization_url

@app.post("/api/google/oauth/revoke", tags=["Google OAuth"], status_code=status.HTTP_204_NO_CONTENT)
async def google_oauth_revoke(
    revoke_data: GoogleOAuthRevokeRequest, # Changed from product: str
    db: Session = Depends(get_db),
    token: str = Depends(get_token_header) 
):
    """
    Revokes the Google OAuth token for the specified product for the current user.
    """
    try:
        current_user: UserModel = await get_current_user(token=token, db=db)
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=f"Authentication required: {e.detail}")

    if not current_user: 
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")

    try:
        service_name_enum = GoogleServiceModel(revoke_data.product.lower()) # Use revoke_data.product
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid product specified. Use 'search_console' or 'ga4'.")

    oauth_service = GoogleOAuthService(db=db)
    revoked = await oauth_service.revoke_token(
        user_email=current_user.email,
        service_name=service_name_enum
    )

    if not revoked:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to revoke Google token properly. Please try again or contact support if the issue persists.")
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get("/api/search-console/sites", tags=["Google Search Console"])
async def list_search_console_sites(
    request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(get_token_header) 
):
    """
    Lists all sites (properties) the authenticated user has access to in Google Search Console.
    """
    try:
        current_user: UserModel = await get_current_user(token=token, db=db)
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=f"Authentication required: {e.detail}")

    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")

    sc_service = SearchConsoleService(db=db)
    try:
        sites = await sc_service.list_sites(user_email=current_user.email)
        # If service call is successful, sites will be a list (possibly empty)
        return {"sites": sites}
    except HTTPException as e:
        # Re-raise the HTTPException thrown by the service layer
        # This will include 403 if not connected (handled by get_valid_access_token if token missing initially)
        # or specific errors from Google API (400, 401, 403, 429, 500, 503 etc.)
        # or 503 if a RequestError occurred during connection.
        raise e
    except Exception as e:
        correlation_id = getattr(request.state, "correlation_id", "N/A")
        log_message = f"Unexpected error in list_search_console_sites for user {current_user.email} [CorrelationID: {correlation_id}]: {e}"
        logger.error(log_message, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected internal error occurred.")

@app.get("/api/ga4/account-summaries", tags=["Google Analytics 4"])
async def list_ga4_account_summaries(
    db: Session = Depends(get_db),
    token: str = Depends(get_token_header) 
):
    """
    Lists all account summaries (accounts, properties, data streams) 
    the authenticated user has access to in Google Analytics 4.
    """
    try:
        current_user: UserModel = await get_current_user(token=token, db=db)
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=f"Authentication required: {e.detail}")

    analytics_service = AnalyticsService(db=db)
    account_summaries = await analytics_service.list_account_summaries(user_email=current_user.email)

    if account_summaries is None:
        oauth_service = GoogleOAuthService(db=db) 
        token_exists = oauth_service.token_repo.get_token(current_user.email, GoogleServiceModel.GOOGLE_ANALYTICS_4)
        if not token_exists:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Google Analytics 4 not connected for this user. Please connect it first via the OAuth flow."
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not retrieve account summaries from Google Analytics at this time. Please try again later."
        )

    return {"account_summaries": account_summaries}

# New Pydantic model for Search Console Query request body
class SearchConsoleQueryRequest(BaseModel):
    startDate: str = Field(..., examples=["2023-01-01"], description="Start date in YYYY-MM-DD format.")
    endDate: str = Field(..., examples=["2023-01-31"], description="End date in YYYY-MM-DD format.")
    dimensions: List[str] = Field(..., examples=[["query", "page"]], description="List of dimensions to group by.")
    dimensionFilterGroups: Optional[List[Dict[str, Any]]] = Field(None, description="Optional. Filters for dimensions.")
    aggregationType: Optional[str] = Field(None, description="Optional. How to aggregate the data.")
    rowLimit: Optional[int] = Field(1000, examples=[100], description="Optional. Number of rows to return.")
    startRow: Optional[int] = Field(0, description="Optional. Zero-based index of the first row to return.")
    type: Optional[str] = Field(None, examples=["web", "image", "video", "news", "discover", "googleNews"], description="Optional. The search type.")
    dataState: Optional[str] = Field(None, examples=["all", "final"], description="Optional. Indicates if you want data for which freshness is guaranteed.")

@app.post("/api/search-console/sites/{site_url_param}/query", tags=["Google Search Console"])
async def query_search_console_analytics(
    site_url_param: str, # This will capture the full path for site_url, e.g., sc-domain:example.com or https://example.com/
    query_request: SearchConsoleQueryRequest,
    db: Session = Depends(get_db),
    token: str = Depends(get_token_header)
):
    """
    Queries the Google Search Console searchAnalytics.query API for a specific site.
    The `site_url_param` in the path should be the site identifier from Search Console,
    e.g., 'sc-domain:example.com' or 'https://www.example.com/'.
    """
    try:
        current_user: UserModel = await get_current_user(token=token, db=db)
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=f"Authentication required: {e.detail}")

    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")

    sc_service = SearchConsoleService(db=db)
    
    try:
        # The site_url_param is already URL-decoded by FastAPI from the path.
        query_result = await sc_service.query_search_analytics(
            user_email=current_user.email,
            site_url=site_url_param, 
            request_body=query_request.model_dump(exclude_none=True)
        )
        # If service call is successful, query_result will be the data from Google
        return query_result
    except HTTPException as e:
        # Re-raise the HTTPException thrown by the service layer
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in query_search_console_analytics for user {current_user.email}, site {site_url_param}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected internal error occurred.")

# Pydantic models for GA4 RunReportRequest
class GA4DateRange(BaseModel):
    startDate: str = Field(..., examples=["2023-10-01", "7daysAgo"])
    endDate: str = Field(..., examples=["2023-10-31", "today"])
    name: Optional[str] = None

class GA4Dimension(BaseModel):
    name: str = Field(..., examples=["city", "country", "date"])
    dimensionExpression: Optional[Dict[str, Any]] = None

class GA4MetricOrdering(BaseModel):
    metricName: str
    desc: Optional[bool] = False

class GA4DimensionOrdering(BaseModel):
    dimensionName: str
    desc: Optional[bool] = False

class GA4OrderBy(BaseModel):
    metric: Optional[GA4MetricOrdering] = None
    dimension: Optional[GA4DimensionOrdering] = None
    pivot: Optional[Dict[str, Any]] = None
    desc: Optional[bool] = False # If true, sorts by descending order.

class GA4Metric(BaseModel):
    name: str = Field(..., examples=["activeUsers", "screenPageViews", "sessions"])
    expression: Optional[str] = None
    invisible: Optional[bool] = False

class GA4FilterStringFilter(BaseModel):
    matchType: str = Field("EXACT", examples=["EXACT", "CONTAINS", "BEGINS_WITH", "ENDS_WITH", "FULL_REGEXP", "PARTIAL_REGEXP"])
    value: str
    caseSensitive: Optional[bool] = False

class GA4FilterInListFilter(BaseModel):
    values: List[str]
    caseSensitive: Optional[bool] = False

# class GA4FilterNumericValue(BaseModel): # Part of a more complex NumericFilter or BetweenFilter
#     int64Value: Optional[str] = None
#     doubleValue: Optional[float] = None

# class GA4FilterBetweenFilter(BaseModel):
#     fromValue: GA4FilterNumericValue
#     toValue: GA4FilterNumericValue

class GA4Filter(BaseModel):
    fieldName: str
    stringFilter: Optional[GA4FilterStringFilter] = None
    inListFilter: Optional[GA4FilterInListFilter] = None
    # numericFilter: Optional[Dict[str, Any]] = None # Placeholder for NumericFilter
    # betweenFilter: Optional[GA4FilterBetweenFilter] = None # Placeholder for BetweenFilter

class GA4FilterExpression(BaseModel):
    andGroup: Optional['GA4FilterExpressionList'] = None
    orGroup: Optional['GA4FilterExpressionList'] = None
    notExpression: Optional['GA4FilterExpression'] = None
    filter: Optional[GA4Filter] = None

class GA4FilterExpressionList(BaseModel):
    expressions: List[GA4FilterExpression]

GA4FilterExpression.model_rebuild() # For forward references

class GA4RunReportRequest(BaseModel):
    dimensions: Optional[List[GA4Dimension]] = Field(None, examples=[[{"name": "country"}]])
    metrics: Optional[List[GA4Metric]] = Field(None, examples=[[{"name": "activeUsers"}]])
    dateRanges: Optional[List[GA4DateRange]] = Field(None, examples=[[{"startDate": "7daysAgo", "endDate": "today"}]])
    dimensionFilter: Optional[GA4FilterExpression] = None
    metricFilter: Optional[GA4FilterExpression] = None
    offset: Optional[str] = Field(None, description="The row count of the start row. The first row is counted as row 0.") # String for int64
    limit: Optional[str] = Field(None, description="The number of rows to return. If unspecified, 10,000 rows are returned.") # String for int64
    metricAggregations: Optional[List[str]] = Field(None, description="Aggregation of metrics. Accepted values: TOTAL, MINIMUM, MAXIMUM, COUNT") # e.g. ["TOTAL", "MAXIMUM"]
    orderBys: Optional[List[GA4OrderBy]] = None
    currencyCode: Optional[str] = Field(None, examples=["USD"])
    # cohortSpec: Optional[Dict[str, Any]] = None # Complex, use Dict or dedicated model
    keepEmptyRows: Optional[bool] = False
    returnPropertyQuota: Optional[bool] = False

@app.post("/api/ga4/properties/{property_id}/run-report", tags=["Google Analytics 4"])
async def run_ga4_report_endpoint(
    property_id: str,
    report_request: GA4RunReportRequest,
    db: Session = Depends(get_db),
    token: str = Depends(get_token_header)
):
    """
    Runs a report against the Google Analytics Data API for a specific GA4 property.
    The `property_id` is the ID of the GA4 Property (e.g., "123456789").
    The request body should conform to the GA4 RunReportRequest schema.
    """
    try:
        current_user: UserModel = await get_current_user(token=token, db=db)
    except HTTPException as e:
        # This will be re-raised by the service if auth fails there too,
        # but good to have an early check.
        raise HTTPException(status_code=e.status_code, detail=f"Authentication required: {e.detail}")

    if not current_user: # Should be caught by get_current_user, but as a safeguard
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")

    analytics_service = AnalyticsService(db=db)
    
    try:
        # Convert Pydantic model to dict, excluding unset fields to send a clean request to Google
        request_body_dict = report_request.model_dump(exclude_none=True)
        
        report_data = await analytics_service.run_ga4_report(
            user_email=current_user.email,
            property_id=property_id,
            report_request=request_body_dict
        )

        if report_data is None: # Should be handled by exceptions in service now
            # Check if the token exists to differentiate
            oauth_service = GoogleOAuthService(db=db)
            token_exists = oauth_service.token_repo.get_token(current_user.email, GoogleServiceModel.GOOGLE_ANALYTICS_4)
            if not token_exists:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Google Analytics 4 not connected for this user. Please connect it first."
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not retrieve report from Google Analytics at this time. Ensure the Property ID is correct and you have access."
            )
        return report_data
    except HTTPException as e: # Catch exceptions from the service (like 401, 403, 500, 503 from Google)
        raise e # Re-raise them
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error in run_ga4_report_endpoint for property {property_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal server error occurred.")

if __name__ == "__main__":
    print("Starting FastAPI server...")
    print("Ensure .env file has OPENAI_API_KEY and SECRET_KEY")
    print("Access the chat interface at http://localhost:8000")
    
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
