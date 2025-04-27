import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
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
from auth import get_current_user, create_access_token, api_key_query

# Database and Models
from database import get_db, engine, SessionLocal
from models import Base, User
from dto import CreateUserDto, UserDto, LoginDto

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

# Simple HTML page for HTTP client
html = """
<!DOCTYPE html>
<html>
<head><title>Agency Chat</title></head>
<body>
    <h1>HTTP Chat with Agency</h1>
    <div id="loginSection">
        <h2>Login</h2>
        <form action="" onsubmit="loginUser(event)">
            <label>Username: <input type="text" id="username" autocomplete="off" value="testuser"/></label>
            <label>Password: <input type="password" id="password" autocomplete="off"/></label>
            <button>Login</button>
        </form>
        <div id="loginStatus"></div>
    </div>

    <div id="registerSection">
        <h2>Register</h2>
        <form action="" onsubmit="registerUser(event)">
            <label>Username: <input type="text" id="regUsername" autocomplete="off"/></label><br>
            <label>First Name: <input type="text" id="firstName" autocomplete="off"/></label><br>
            <label>Last Name: <input type="text" id="lastName" autocomplete="off"/></label><br>
            <label>Email: <input type="email" id="email" autocomplete="off"/></label><br>
            <label>Password: <input type="password" id="regPassword" autocomplete="off"/></label><br>
            <button>Register</button>
        </form>
        <div id="registerStatus"></div>
    </div>

    <div id="chatSection" style="display: none;">
        <h2>Chat</h2>
        <div>Token: <span id="tokenDisplay"></span></div>
        <form action="" onsubmit="sendMessage(event)">
            <label>Conversation ID: <input type="text" id="conversationId" autocomplete="off" value="conv-1"/></label><br>
            <label>Message: <input type="text" id="messageText" autocomplete="off"/></label>
            <button>Send</button>
        </form>
        <ul id='messages'></ul>
    </div>

    <script>
        var currentToken = null;

        async function registerUser(event) {
            event.preventDefault();
            const registerStatus = document.getElementById("registerStatus");
            try {
                const response = await fetch('/register', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        username: document.getElementById("regUsername").value,
                        first_name: document.getElementById("firstName").value,
                        last_name: document.getElementById("lastName").value,
                        email: document.getElementById("email").value,
                        password: document.getElementById("regPassword").value
                    })
                });
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || `Registration failed: ${response.statusText}`);
                }
                registerStatus.textContent = "Registration successful! You can now login.";
            } catch (error) {
                registerStatus.textContent = `Registration error: ${error.message}`;
                console.error("Registration error:", error);
            }
        }

        async function loginUser(event) {
            event.preventDefault();
            const username = document.getElementById("username").value;
            const password = document.getElementById("password").value;
            const loginStatus = document.getElementById("loginStatus");
            try {
                const response = await fetch('/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    body: `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`
                });
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || `Login failed: ${response.statusText}`);
                }
                const data = await response.json();
                currentToken = data.access_token;
                loginStatus.textContent = "Login successful!";
                document.getElementById("tokenDisplay").textContent = currentToken;
                document.getElementById("loginSection").style.display = "none";
                document.getElementById("registerSection").style.display = "none";
                document.getElementById("chatSection").style.display = "block";
            } catch (error) {
                loginStatus.textContent = `Login error: ${error.message}`;
                console.error("Login error:", error);
            }
        }

        async function sendMessage(event) {
            event.preventDefault();
            const conversationInput = document.getElementById("conversationId");
            const messageInput = document.getElementById("messageText");
            const conversationId = conversationInput.value;
            
            if (!currentToken) {
                addMessage("System: Please login first.");
                return;
            }

            try {
                addMessage(`You: ${messageInput.value}`);
                
                const response = await fetch(`/chat/${conversationId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${currentToken}`
                    },
                    body: JSON.stringify({
                        message: messageInput.value
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || `Chat request failed: ${response.statusText}`);
                }

                const data = await response.json();
                addMessage(`Agency: ${data.response}`);
                messageInput.value = '';
            } catch (error) {
                addMessage(`System: Error - ${error.message}`);
                console.error("Chat error:", error);
            }
        }

        function addMessage(message) {
            const messages = document.getElementById('messages');
            const messageItem = document.createElement('li');
            messageItem.textContent = message;
            messages.appendChild(messageItem);
            // Scroll to bottom
            messages.scrollTop = messages.scrollHeight;
        }
    </script>
</body>
</html>
"""

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
async def register_user(user_data: CreateUserDto, db: Session = Depends(get_db)):
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    hashed_password = pwd_context.hash(user_data.password)
    db_user = User(
        username=user_data.username,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        email=user_data.email,
        password=hashed_password
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return UserDto(
        username=db_user.username,
        first_name=db_user.first_name,
        last_name=db_user.last_name,
        email=db_user.email
    )

@app.post("/login", tags=["Authentication"])
async def login_for_access_token(
    login_data: LoginDto,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == login_data.username).first()
    if not user or not pwd_context.verify(login_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    userDto = UserDto(
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email
    )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "user": userDto}

@app.post("/chat/{conversation_id}", tags=["Chat"])
async def chat_endpoint(
    conversation_id: str,
    request: dict,
    token: str = Depends(api_key_query),
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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 