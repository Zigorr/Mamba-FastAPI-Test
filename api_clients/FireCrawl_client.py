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

    _app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
    
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

