import httpx
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode
import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.config import settings
from models import GoogleService
from repositories import GoogleOAuthTokenRepository
# Assuming Valkey for state management, need to import get_valkey_connection
from database import get_valkey_connection # Or however you get your Valkey/Redis connection

logger = logging.getLogger(__name__)

# Google OAuth2 Endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Scopes (as per the PDF document)
SCOPES_BASE = ["openid", "email", "profile"]
SCOPES_SEARCH_CONSOLE = ["https://www.googleapis.com/auth/webmasters.readonly"]
SCOPES_GA4 = ["https://www.googleapis.com/auth/analytics.readonly"]

# State TTL in Valkey/Redis (e.g., 10 minutes)
STATE_TTL_SECONDS = 600

class GoogleOAuthService:
    def __init__(self, db: Session):
        self.db = db
        self.token_repo = GoogleOAuthTokenRepository(db)

    def _get_redirect_uri(self) -> str:
        """Constructs the full redirect URI from settings."""
        return f"{settings.APP_BASE_URL.rstrip('/')}{settings.GOOGLE_OAUTH_CALLBACK_PATH}"

    async def build_authorization_url(self, user_email: str, service_name: GoogleService, valkey_conn) -> str:
        """
        Builds the Google OAuth2 authorization URL and stores state.
        """
        state_data = {
            "user_email": user_email,
            "service_name": service_name.value, # Store the string value of the enum
            "csrf_token": str(uuid.uuid4()) # Basic CSRF token
        }
        state_key = str(uuid.uuid4()) # Unique key for storing state in Valkey

        # Store state in Valkey with TTL
        await valkey_conn.setex(f"oauth_state:{state_key}", STATE_TTL_SECONDS, json.dumps(state_data))

        scopes_for_service = SCOPES_BASE[:] # Start with base scopes
        if service_name == GoogleService.SEARCH_CONSOLE:
            scopes_for_service.extend(SCOPES_SEARCH_CONSOLE)
        elif service_name == GoogleService.GOOGLE_ANALYTICS_4:
            scopes_for_service.extend(SCOPES_GA4)
        else:
            raise ValueError("Invalid service_name provided for OAuth.")

        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": self._get_redirect_uri(),
            "response_type": "code",
            "scope": " ".join(scopes_for_service),
            "access_type": "offline",  # To get a refresh token
            "prompt": "consent",       # To ensure refresh token is issued, and user re-consents if needed
            "state": state_key,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str, state_key_from_google: str, valkey_conn) -> Dict[str, Any]:
        """
        Exchanges authorization code for tokens and saves them.
        Verifies the state.
        """
        # Retrieve and verify state
        stored_state_json = await valkey_conn.get(f"oauth_state:{state_key_from_google}")
        if not stored_state_json:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state.")
        
        # Delete state from Valkey after retrieval to prevent reuse
        await valkey_conn.delete(f"oauth_state:{state_key_from_google}")

        stored_state_data = json.loads(stored_state_json)
        user_email = stored_state_data.get("user_email")
        service_name_str = stored_state_data.get("service_name")
        # csrf_token = stored_state_data.get("csrf_token") # Could verify this if sent separately

        if not user_email or not service_name_str:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state content.")

        service_name = GoogleService(service_name_str) # Convert string back to Enum

        token_payload = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": self._get_redirect_uri(),
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(GOOGLE_TOKEN_URL, data=token_payload)

        if response.status_code != 200:
            error_detail = response.json().get("error_description", "Failed to exchange code for token.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Google OAuth Error: {error_detail}")

        token_data = response.json()
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token") # refresh_token is not always returned
        expires_in = token_data["expires_in"] # seconds
        granted_scopes = token_data.get("scope", "").split(" ")

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        self.token_repo.create_or_update_token(
            user_email=user_email,
            service_name=service_name,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=granted_scopes
        )
        # For frontend redirection or confirmation
        return {"user_email": user_email, "service_name": service_name.value, "status": "success"}

    async def refresh_access_token(self, user_email: str, service_name: GoogleService) -> Optional[str]:
        """
        Refreshes an access token using the stored refresh token.
        Returns the new access token or None if refresh fails or no refresh token.
        """
        logger.info(f"Attempting to refresh token for user {user_email}, service {service_name.value}")
        stored_token_orm = self.token_repo.get_token(user_email=user_email, service_name=service_name)

        if not stored_token_orm or not stored_token_orm.refresh_token:
            logger.warning(f"No refresh token found for user {user_email}, service {service_name.value} to refresh.")
            return None

        payload = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": stored_token_orm.refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(GOOGLE_TOKEN_URL, data=payload)

        if response.status_code != 200:
            error_data = response.json()
            error_description = error_data.get("error_description", "Failed to refresh token.")
            error_type = error_data.get("error")
            logger.error(f"Google OAuth Error refreshing token for {user_email}, {service_name.value}: {error_description} (Type: {error_type}) - Status: {response.status_code} - Response: {response.text}")
            
            if error_type == "invalid_grant":
                logger.warning(f"Refresh token for {user_email}, {service_name.value} is invalid. Clearing stored refresh token and invalidating access token.")
                self.token_repo.create_or_update_token(
                    user_email=user_email,
                    service_name=service_name,
                    access_token="",  # Invalidate access token
                    refresh_token=None, 
                    expires_at=datetime.now(timezone.utc) - timedelta(days=1), # Set to a past expiry
                    scopes=stored_token_orm.scopes or []
                )
            return None

        response.raise_for_status()
        token_data = response.json()

        new_access_token = token_data.get("access_token")
        new_expires_in_seconds = token_data.get("expires_in")
        # Check if Google returned a new refresh token (rotation)
        new_refresh_token_from_google = token_data.get("refresh_token")

        if not new_access_token or new_expires_in_seconds is None:
            logger.error(f"Google token refresh response missing access_token or expires_in for user {user_email}, service {service_name.value}. Response: {token_data}")
            return None

        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=new_expires_in_seconds)

        # Determine which refresh token to store: the new one if provided, otherwise the existing one.
        refresh_token_to_store = new_refresh_token_from_google if new_refresh_token_from_google else stored_token_orm.refresh_token
        if new_refresh_token_from_google:
            logger.info(f"Received new refresh token from Google for user {user_email}, service {service_name.value}. Old one will be overwritten.")

        self.token_repo.create_or_update_token(
            user_email=user_email,
            service_name=service_name,
            access_token=new_access_token,
            refresh_token=refresh_token_to_store, # Pass the potentially new refresh token
            expires_at=new_expires_at,
            scopes=stored_token_orm.scopes # Assuming scopes don't change on refresh
        )
        logger.info(f"Successfully refreshed access token for user {user_email}, service {service_name.value}.")
        return new_access_token

    async def get_valid_access_token(self, user_email: str, service_name: GoogleService) -> Optional[str]:
        """
        Retrieves a stored access token. If it's expired or nearing expiry,
        it attempts to refresh it.
        Returns a valid access token or None if not available or refresh fails.
        """
        logger.info(f"Getting valid access token for user {user_email}, service {service_name.value}")
        stored_token_orm = self.token_repo.get_token(user_email=user_email, service_name=service_name)

        if not stored_token_orm:
            logger.warning(f"No token found for user {user_email}, service {service_name.value}.")
            return None

        buffer_seconds = 300 
        if datetime.now(timezone.utc) >= (stored_token_orm.expires_at - timedelta(seconds=buffer_seconds)):
            logger.info(f"Access token for {user_email}, {service_name.value} expired or nearing expiry. Attempting refresh.")
            new_access_token = await self.refresh_access_token(user_email, service_name)
            if not new_access_token:
                logger.error(f"Failed to refresh access token for {user_email}, {service_name.value}.")
            return new_access_token
        
        logger.info(f"Returning stored, valid access token for user {user_email}, service {service_name.value}.")
        return stored_token_orm.access_token

    async def revoke_token(self, user_email: str, service_name: GoogleService) -> bool:
        """
        Revokes a Google OAuth token with Google and deletes it from the local database.
        Returns True if successful or token was already invalid/not found locally, False otherwise.
        """
        logger.info(f"Attempting to revoke token for user {user_email}, service {service_name.value}")
        stored_token_orm = self.token_repo.get_token(user_email=user_email, service_name=service_name)

        if not stored_token_orm:
            logger.warning(f"No token found locally for user {user_email}, service {service_name.value}. Assuming already revoked or not connected.")
            return True

        token_to_revoke = stored_token_orm.refresh_token or stored_token_orm.access_token

        if not token_to_revoke:
            logger.warning(f"No actual token string (access or refresh) found to revoke for {user_email}, {service_name.value}.")
            self.token_repo.delete_token(user_email, service_name)
            return True

        payload = {"token": token_to_revoke}
        success_on_google_side = False
        async with httpx.AsyncClient() as client:
            response = await client.post(GOOGLE_REVOKE_URL, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})

        if response.status_code == 200:
            logger.info(f"Token revocation request to Google successful (or token already invalid) for {user_email}, {service_name.value}.")
            success_on_google_side = True
        elif response.status_code == 400:
            logger.error(f"Google OAuth Revoke Error (Bad Request) for {user_email}, {service_name.value}: {response.text}")
            success_on_google_side = True 
        else:
            logger.error(f"Google OAuth Revoke Error for {user_email}, {service_name.value}: Status {response.status_code} - {response.text}")

        if success_on_google_side:
            deleted_locally = self.token_repo.delete_token(user_email, service_name)
            if deleted_locally:
                logger.info(f"Successfully deleted local token for {user_email}, {service_name.value} after revocation attempt.")
            else:
                logger.warning(f"Local token for {user_email}, {service_name.value} was not found for deletion, though revocation attempt was made.")
            return True
        
        return False 