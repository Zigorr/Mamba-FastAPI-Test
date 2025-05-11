# services/search_console_service.py
import httpx
from typing import Optional, List, Dict, Any
import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models import GoogleService
from services.google_oauth_service import GoogleOAuthService # To get valid access tokens

logger = logging.getLogger(__name__)

# Google Search Console API Endpoint
SEARCH_CONSOLE_SITES_LIST_URL = "https://www.googleapis.com/webmasters/v3/sites"

class SearchConsoleService:
    def __init__(self, db: Session):
        self.db = db
        self.google_oauth_service = GoogleOAuthService(db)

    async def list_sites(self, user_email: str) -> Optional[List[Dict[str, Any]]]:
        """
        Lists the sites (properties) the user has access to in Google Search Console.
        """
        access_token = await self.google_oauth_service.get_valid_access_token(
            user_email=user_email,
            service_name=GoogleService.SEARCH_CONSOLE
        )

        if not access_token:
            logger.error(f"No valid access token available for Search Console for user {user_email}.")
            return None

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(SEARCH_CONSOLE_SITES_LIST_URL, headers=headers)
                response.raise_for_status() 
                
                sites_data = response.json()
                return sites_data.get("siteEntry", [])
            except httpx.HTTPStatusError as e:
                error_content = e.response.text
                try:
                    error_json = e.response.json()
                    # Google Search Console API v3 errors are often simpler, directly in response or under 'error'
                    if "error" in error_json and "message" in error_json["error"]:
                         error_message = error_json["error"]["message"]
                    elif "message" in error_json: # Sometimes it's just a message field
                        error_message = error_json["message"]
                    else:
                        error_message = error_content.strip() # Fallback to text
                except ValueError: # Not JSON
                    error_message = error_content.strip()
                
                logger.error(f"HTTP error calling Google Search Console API (list_sites) for user {user_email}: {e.response.status_code} - {error_message}", exc_info=True)
                raise HTTPException(status_code=e.response.status_code, detail=f"Google Search Console API Error: {error_message}")
            except httpx.RequestError as e:
                logger.error(f"Request error calling Google Search Console API (list_sites) for user {user_email}: {e}", exc_info=True)
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Error connecting to Google Search Console API.")
            except Exception as e:
                logger.error(f"Unexpected error listing Search Console sites for {user_email}: {e}", exc_info=True)
                return None 

    async def query_search_analytics(
        self, 
        user_email: str, 
        site_url: str, 
        request_body: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Performs a searchAnalytics.query against the Google Search Console API.
        """
        access_token = await self.google_oauth_service.get_valid_access_token(
            user_email=user_email,
            service_name=GoogleService.SEARCH_CONSOLE
        )

        if not access_token:
            logger.error(f"No valid access token available for Search Console query for user {user_email}, site {site_url}.")
            return None

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        # Ensure site_url is properly encoded for the path. 
        # For example, slashes should be %2F. httpx might handle some of this.
        # A common quick fix for site URLs like 'https://example.com/' is to replace '/' with '%2F'
        # However, Search Console often uses 'sc-domain:example.com' which doesn't need such encoding.
        # Assuming site_url is passed in a format that's safe or pre-encoded if necessary for path.
        # For this example, let's use a simple replacement that works for 'http(s)://' type URLs if they are used.
        # If site_url is like 'sc-domain:example.com', this replacement is harmless.
        encoded_site_url = site_url.replace('/', '%2F')
        api_url = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site_url}/searchAnalytics/query"

        logger.info(f"Querying Search Console Analytics for user {user_email}, site {site_url} (encoded: {encoded_site_url}), url: {api_url}, body: {request_body}")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(api_url, headers=headers, json=request_body)
                response.raise_for_status() 
                
                query_data = response.json()
                return query_data
            except httpx.HTTPStatusError as e:
                error_content = e.response.text
                try:
                    error_json = e.response.json()
                    if "error" in error_json and "message" in error_json["error"]:
                         error_message = error_json["error"]["message"]
                    elif "message" in error_json:
                        error_message = error_json["message"]
                    else:
                        error_message = error_content.strip()
                except ValueError: 
                    error_message = error_content.strip()

                logger.error(f"HTTP error querying Search Console Analytics for user {user_email}, site {site_url}: {e.response.status_code} - {error_message}", exc_info=True)
                raise HTTPException(status_code=e.response.status_code, detail=f"Google Search Console API Error: {error_message}")
            except httpx.RequestError as e:
                logger.error(f"Request error querying Search Console Analytics for user {user_email}, site {site_url}: {e}", exc_info=True)
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Error connecting to Google Search Console API for query.")
            except Exception as e:
                logger.error(f"Unexpected error querying Search Console Analytics for {user_email}, site {site_url}: {e}", exc_info=True)
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while querying Search Console analytics.") 