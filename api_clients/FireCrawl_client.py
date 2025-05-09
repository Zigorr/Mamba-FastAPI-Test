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
    
    @staticmethod
    def extract_products_from_website(url: str) -> str:
        class PersonaSchema(BaseModel):
            persona: str
            description: str
            priority: int
        class ProductSchema(BaseModel):
            url: str
            language: str
            name: str
            description: str
            priority: int
        class ExtractSchema(BaseModel):
            products: list[ProductSchema]
            targe_personas: list[PersonaSchema]
        prompt = f"""
        Scrape the company website for:
        - products: where each product has url, locale language in ISO 639-1 codes, its official brand name, a very short description for the product, and a priority score from 1-10 measuring how important sales of this product are to the company.
        - target_personas: where each persona has its name, short description, and a priority score from 1-10 measuring how important this persona matters to the business. 
        """
        return FireCrawlClient._extract(url, prompt, ExtractSchema)

if __name__ == "__main__":

    import json
    site_url = "https://www.logitechg.com/*"
    url = "https://www.logitechg.com/en-nz/products/gaming-mice/g402-hyperion-fury-fps-gaming-mouse.910-004070.html"
    response = FireCrawlClient.extract_products_from_website(site_url)
    print(response)
    json.dump(response, open("extracted_products.json", "w"), indent=4)

