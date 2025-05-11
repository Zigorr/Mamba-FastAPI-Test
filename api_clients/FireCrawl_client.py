# Install with pip install firecrawl-py
from firecrawl import FirecrawlApp, ScrapeOptions
from pydantic import BaseModel, Field
from typing import Any, Optional, List

from dotenv import load_dotenv
import os
import logging
import pandas as pd

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
    def _crawl(url: str) -> str:
        data = FireCrawlClient._app.crawl_url(
            url, 
            limit=10, 
            scrape_options=ScrapeOptions(formats=['markdown']),
        )
        if data.success:
            results = []
            for document in data.data:
                item = {}
                item['url'] = document.metadata['url']
                item['markdown'] = document.markdown
                results.append(item)
            return results
        else:
            raise Exception(data.error)
    
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
        url = f"{url}/*"
        class ProductSchema(BaseModel):
            url: str
            language: str
            name: str
            description: str
            priority: int
        class ExtractSchema(BaseModel):
            products: list[ProductSchema]
            company_summary: str

        prompt = """
        Scrape the company website for the following:
        - products: Each product must include its URL, locale language using ISO 639-1 codes (e.g., "en"), its official brand name, a *very short* description of the product, and a priority score from 1 to 10 measuring the product's importance to the company.
        - company_summary: A concise but descriptive summary of who this company is, what they do, what types of products/services they offer.
        """
        response = FireCrawlClient._extract(url, prompt, ExtractSchema)
        df = pd.DataFrame(response['products'])

        # Filter for "en" language using regex
        df_filtered = df[df['language'].str.match(r'^en.*$')]
        # Remove duplicates based on url
        df_filtered = df_filtered.drop_duplicates(subset=['url'])
        df_filtered = df_filtered[df_filtered['url'].str.match(r'^https.*$')]
        # Sort by priority in descending order
        df_filtered = df_filtered.sort_values('priority', ascending=False)
        # Reset index
        df_filtered = df_filtered.reset_index(drop=True)
        # Handle Unicode characters by normalizing
        df_filtered['name'] = df_filtered['name'].apply(lambda x: x.encode('ascii', 'ignore').decode('ascii'))
        df_filtered['description'] = df_filtered['description'].apply(lambda x: x.encode('ascii', 'ignore').decode('ascii'))
        response['products'] = df_filtered.to_dict('records')

        return response

if __name__ == "__main__":

    import json
    site_url = "https://www.logitechg.com"
    url = "https://www.logitechg.com/en-nz/products/gaming-mice/g402-hyperion-fury-fps-gaming-mouse.910-004070.html"
    #response = FireCrawlClient.extract_products_from_website(site_url)
    response = FireCrawlClient._crawl(site_url)
    print(response)
    json.dump(response, open("crawled_data.json", "w"), indent=4)

