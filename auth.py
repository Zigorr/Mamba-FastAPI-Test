from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer, APIKeyQuery
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from database import get_db
from models import User
from typing import Optional
from passlib.context import CryptContext

load_dotenv()

# Configuration (load secret key from environment)
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 100

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY not set in environment variables or .env file")

# --- JWT Token Functions --- 

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = {"email": email}
    except JWTError:
        raise credentials_exception
    return token_data

# --- FastAPI Dependency --- 

# Use APIKeyQuery to read token from query parameter named 'token' for WebSocket
api_key_query = APIKeyQuery(name="token", auto_error=False)

async def get_current_user(token: str = Depends(api_key_query), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}, # Although not strictly Bearer for WebSocket query param
    )
    if token is None:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Not authenticated - token query parameter missing"
        )
    
    token_data = verify_token(token, credentials_exception)
    user = db.query(User).filter(User.email == token_data["email"]).first()
    if user is None:
        raise credentials_exception
    return user # Return the user ORM object 

async def get_token_header(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Authorization header"
        )
    return authorization.split(" ")[1] 