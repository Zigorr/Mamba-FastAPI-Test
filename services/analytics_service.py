# services/analytics_service.py
import httpx
from typing import Optional, List, Dict, Any
import logging
from fastapi import HTTPException, status

from sqlalchemy.orm import Session

from models import GoogleService
from services.google_oauth_service import GoogleOAuthService # To get valid access tokens

logger = logging.getLogger(__name__)

# Google Analytics Admin API Endpoint
ANALYTICS_ADMIN_ACCOUNT_SUMMARIES_URL = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"
# Google Analytics Data API Endpoint (for future use, e.g., running reports)
# ANALYTICS_DATA_RUN_REPORT_URL_TEMPLATE = "https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"

class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db
        self.google_oauth_service = GoogleOAuthService(db)

    async def list_account_summaries(self, user_email: str) -> Optional[List[Dict[str, Any]]]:
        """
        Lists the account summaries the user has access to in Google Analytics (GA4).
        Account summaries include accounts, properties, and data streams.
        """
        access_token = await self.google_oauth_service.get_valid_access_token(
            user_email=user_email,
            service_name=GoogleService.GOOGLE_ANALYTICS_4 
        )

        if not access_token:
            logger.error(f"No valid access token available for Google Analytics for user {user_email}.")
            return None

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        params = {
            "pageSize": 200 
        }

        all_account_summaries = []
        next_page_token = None

        async with httpx.AsyncClient() as client:
            try:
                while True:
                    current_params = params.copy()
                    if next_page_token:
                        current_params["pageToken"] = next_page_token
                    
                    response = await client.get(ANALYTICS_ADMIN_ACCOUNT_SUMMARIES_URL, headers=headers, params=current_params)
                    response.raise_for_status() 
                    
                    data = response.json()
                    all_account_summaries.extend(data.get("accountSummaries", []))
                    
                    next_page_token = data.get("nextPageToken")
                    if not next_page_token:
                        break 
                
                return all_account_summaries
            except httpx.HTTPStatusError as e:
                error_content = e.response.text
                try:
                    error_json = e.response.json()
                    error_message = error_json.get("error", {}).get("message", error_content)
                except ValueError:
                    error_message = error_content.strip()
                logger.error(f"HTTP error calling Google Analytics Admin API for user {user_email}: {e.response.status_code} - {error_message}", exc_info=True)
                raise HTTPException(status_code=e.response.status_code, detail=f"Google Analytics API Error: {error_message}")
            except httpx.RequestError as e:
                logger.error(f"Request error calling Google Analytics Admin API for user {user_email}: {e}", exc_info=True)
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Error connecting to Google Analytics Admin API.")
            except Exception as e:
                logger.error(f"Unexpected error listing Google Analytics account summaries for {user_email}: {e}", exc_info=True)
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while listing Google Analytics account summaries.")

    async def run_ga4_report(self, user_email: str, property_id: str, report_request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Runs a report against the Google Analytics Data API v1beta.
        https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport
        """
        access_token = await self.google_oauth_service.get_valid_access_token(
            user_email=user_email,
            service_name=GoogleService.GOOGLE_ANALYTICS_4
        )

        if not access_token:
            logger.error(f"No valid access token available for Google Analytics Data API for user {user_email}, property {property_id}.")
            return None

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        api_url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"

        logger.info(f"Running GA4 report for user {user_email}, property {property_id}, request: {report_request}")

        async with httpx.AsyncClient(timeout=30.0) as client: # Increased timeout for potentially long reports
            try:
                response = await client.post(api_url, headers=headers, json=report_request)
                response.raise_for_status()
                
                report_data = response.json()
                return report_data
            except httpx.HTTPStatusError as e:
                error_content = e.response.text
                try:
                    error_json = e.response.json()
                    error_message = error_json.get("error", {}).get("message", error_content)
                except ValueError:
                    error_message = error_content
                logger.error(f"HTTP error running GA4 report for user {user_email}, property {property_id}: {e.response.status_code} - {error_message}", exc_info=True)
                # Consider raising a specific exception or returning structured error
                raise HTTPException(status_code=e.response.status_code, detail=f"Google Analytics API Error: {error_message}")
            except httpx.RequestError as e:
                logger.error(f"Request error running GA4 report for user {user_email}, property {property_id}: {e}", exc_info=True)
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Error connecting to Google Analytics Data API.")
            except Exception as e:
                logger.error(f"Unexpected error running GA4 report for {user_email}, property {property_id}: {e}", exc_info=True)
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while running the GA4 report.")

    # Placeholder for future method to run reports
    # async def run_ga4_report(self, user_email: str, property_id: str, report_request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    #     pass 