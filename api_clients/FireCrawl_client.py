# Install with pip install firecrawl-py
from firecrawl import FirecrawlApp
from pydantic import BaseModel, Field
from typing import Any, Optional, List

from dotenv import load_dotenv
import os
import logging

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# Define default parameters or constants if needed
DEFAULT_TIMEOUT = 30000  # Example: 30 seconds

class FireCrawlClient:
    """
    A static class to interact with the FireCrawl API.
    Handles authentication and provides methods for specific endpoints.
    Automatically saves responses to a structured directory.
    """
    def __init__(self):
        """Initializes the FireCrawlClient, loading the API key."""
        self.api_key = os.getenv("FIRECRAWL_API_KEY")
        if not self.api_key:
            logger.error("FIRECRAWL_API_KEY environment variable not found.")
            # Raise an error here to make it clear configuration is missing
            raise ValueError("FIRECRAWL_API_KEY is not set in the environment.")
        # Initialize the app instance *here*
        self.app = FirecrawlApp(api_key=self.api_key)
        logger.info("FireCrawlClient initialized.")

    def scrape_url(self, url: str, params: dict = None) -> dict:
        """Scrapes a single URL using Firecrawl."""
        if not self.app: # Should not happen if __init__ succeeded
             raise RuntimeError("FirecrawlApp not initialized.")
        try:
            # Add default timeout if not provided in params
            scrape_params = {'pageOptions': {'timeout': DEFAULT_TIMEOUT}}
            if params:
                 scrape_params.update(params)

            logger.info(f"Scraping URL: {url} with params: {scrape_params}")
            # Use the instance variable self.app
            scraped_data = self.app.scrape_url(url, params=scrape_params)
            logger.info(f"Successfully scraped URL: {url}")
            return scraped_data
        except Exception as e:
            logger.error(f"Error scraping URL {url}: {e}", exc_info=True)
            # Re-raise or return an error structure
            raise

    # Add other methods as needed (e.g., crawl_url)
    def crawl_url(self, url: str, params: dict = None, wait_until_done: bool = True) -> any:
        """Starts a crawl job for a URL using Firecrawl."""
        if not self.app:
            raise RuntimeError("FirecrawlApp not initialized.")
        try:
            # Add default timeout if not provided in params
            crawl_params = {'pageOptions': {'timeout': DEFAULT_TIMEOUT}}
            if params:
                 crawl_params.update(params)

            logger.info(f"Crawling URL: {url} with params: {crawl_params}")
            # Use the instance variable self.app
            job_id = self.app.crawl_url(url, params=crawl_params, wait_until_done=wait_until_done)
            logger.info(f"Successfully started crawl job for URL: {url}. Job ID: {job_id}")

            if wait_until_done:
                 # If waiting, the result is returned directly
                 return job_id
            else:
                 # If not waiting, return the job ID
                 return {"job_id": job_id}

        except Exception as e:
            logger.error(f"Error crawling URL {url}: {e}", exc_info=True)
            raise

    def check_crawl_status(self, job_id: str) -> dict:
         """Checks the status of a crawl job."""
         if not self.app:
              raise RuntimeError("FirecrawlApp not initialized.")
         try:
              logger.info(f"Checking crawl status for job ID: {job_id}")
              status = self.app.check_crawl_status(job_id)
              logger.info(f"Crawl status for job ID {job_id}: {status.get('status')}")
              return status
         except Exception as e:
              logger.error(f"Error checking crawl status for job ID {job_id}: {e}", exc_info=True)
              raise

    @staticmethod
    def _extract(url: str, prompt: str, schema: BaseModel) -> str: 
        data = FireCrawlClient._app.extract(
            urls=[url], 
            prompt=prompt,
            schema=schema.model_json_schema(),
        )
        if data.success:
            return data.data
        else:
            raise Exception(data.error)
    
    @staticmethod
    def extract_product_url_summary(url: str) -> str:
        class ExtractSchema(BaseModel):
            summary: str
        prompt = f"Create a consice summary for this product/service with important/significat information."
        return FireCrawlClient._extract(url, prompt, ExtractSchema)['summary']

if __name__ == "__main__":
    url = "https://www.logitechg.com/en-nz/products/gaming-mice/g402-hyperion-fury-fps-gaming-mouse.910-004070.html"
    print(FireCrawlClient.extract_product_url_summary(url))

