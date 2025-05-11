# Install with pip install firecrawl-py
from pydantic import BaseModel, Field
from typing import Any, Optional, List
from dotenv import load_dotenv
import logging
import openai
import os
import json
import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()
load_dotenv(override=True)

logger = logging.getLogger(__name__)
class OpenAIClient:
    """
    A static class to interact with Open AI API.
    """

    _client = openai.OpenAI()

    @staticmethod
    def _create_tool(name: str, description: str, model: type[BaseModel]) -> dict:
        schema = model.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": schema
            }
        }
    
    @staticmethod
    def _get_structured_completion(tools, choice, system_prompt, content_prompt):
        try:
            response = OpenAIClient._client.chat.completions.create(
                model="gpt-4",
                messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_prompt}
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": choice}}
            )
            print(response.choices[0].message.tool_calls[0].function.arguments)
            return json.loads(response.choices[0].message.tool_calls[0].function.arguments)
        except Exception as e:
            logger.error(f"Error getting structured completion: {e}")
            raise e;
    
    @staticmethod
    def extract_company_data(crawled_data):
        """
        Extract products, company summary, target personas, and competitors all from crawled data in one operation
        
        Args:
            crawled_data: A list of crawled webpage data containing URL and markdown content
            
        Returns:
            A dictionary containing company summary, products, target personas, and competitors
        """
        class Product(BaseModel):
            url: str = Field(..., description="The URL of the product or service page")
            name: str = Field(..., description="The official brand name of the product or service")
            description: str = Field(..., description="A detailed, but concise description of the product or service")
            priority: int = Field(..., description="A priority score from 1-10 (where 1 is lowest priority and 10 is highest)")

        class TargetPersona(BaseModel):
            name: str = Field(..., description="A concise label for the target persona")
            description: str = Field(..., description="A brief description of this target persona")
            priority: int = Field(..., description="A priority score from 1-10 measuring the target persona's importance")

        class Competitor(BaseModel):
            name: str = Field(..., description="The official brand name of the competing company")
            description: str = Field(..., description="A short description of what the competitor does")

        class ComprehensiveExtractInput(BaseModel):
            company_summary: str = Field(..., description="A concise summary of the company based on crawled data")
            products: List[Product] = Field(..., description="List of products or services offered by the company")
            personas: List[TargetPersona] = Field(..., description="List of target personas for the company's products/services")
            competitors: List[Competitor] = Field(..., description="List of competitors to the company")
            
        tools = [
            OpenAIClient._create_tool(
                name="extract_all_data",
                description="Extract comprehensive information from crawled website data",
                model=ComprehensiveExtractInput
            )
        ]
        
        # Prepare crawled data for prompt
        pages_data = []
        try :
            for page in crawled_data:
                # Limit markdown content to reduce token usage
                content_preview = page["markdown"][:3000] + "..." if len(page["markdown"]) > 3000 else page["markdown"]
                pages_data.append(f"URL: {page['url']}\nContent: {content_preview}")
        except Exception as e:
            logger.error(f"Error extracting company data: {e}")
            raise e;
        
        all_pages = "\n\n---\n\n".join(pages_data)
        
        system_prompt = "You are an AI that extracts comprehensive business information from crawled website content."
        content_prompt = f"""
        From the given crawled website data, extract all of the following information:
        
        1. COMPANY SUMMARY:
           A concise summary explaining what the company does, its main products/services, and target audience.
        
        2. PRODUCTS/SERVICES:
           Extract product or service information with these attributes:
           - url: The URL of the product or service page
           - name: The official brand name of the product or service
           - description: A detailed, but concise description of the product or service
           - priority: A priority score from 1-10 (where 1 is lowest priority and 10 is highest)
           Only include actual products (not categories or informational pages).
        
        3. TARGET PERSONAS:
           Identify the key target customer personas for this company with these attributes:
           - name: A concise label for the target persona
           - description: A brief description of this target persona
           - priority: A priority score from 1-10 measuring how important this persona is to the company
        
        4. COMPETITORS:
           Identify the main competitors to this company with these attributes:
           - name: The official brand name of the competing company
           - description: A short description of what they do and how they relate to the company
        
        Crawled Data:
        {all_pages}
        """
        
        response = OpenAIClient._get_structured_completion(
            tools,
            "extract_all_data",
            system_prompt,
            content_prompt
        )
        
        return response
        
    @staticmethod
    def generate_company_data(products_description: str, personas_description: str, competitors_description: str, company_name: str):
        """
        Create structured data from user-provided descriptive strings
        
        Args:
            products_description: A string description of the products/services
            personas_description: A string description of the target personas/customers
            competitors_description: A string description of the competitors
            company_name: Name of the company to use in generating the company summary
            
        Returns:
            A dictionary containing company summary, products, target personas, and competitors
        """
        class Product(BaseModel):
            url: str = Field(..., description="The URL of the product or service page")
            name: str = Field(..., description="The official brand name of the product or service")
            description: str = Field(..., description="A detailed, but concise description of the product or service")
            priority: int = Field(..., description="A priority score from 1-10 (where 1 is lowest priority and 10 is highest)")

        class TargetPersona(BaseModel):
            name: str = Field(..., description="A concise label for the target persona")
            description: str = Field(..., description="A brief description of this target persona")
            priority: int = Field(..., description="A priority score from 1-10 measuring the target persona's importance")

        class Competitor(BaseModel):
            name: str = Field(..., description="The official brand name of the competing company")
            description: str = Field(..., description="A short description of what the competitor does")

        class ComprehensiveExtractInput(BaseModel):
            company_summary: str = Field(..., description="A concise summary of the company based on provided information")
            products: List[Product] = Field(..., description="List of products or services offered by the company")
            personas: List[TargetPersona] = Field(..., description="List of target personas for the company's products/services")
            competitors: List[Competitor] = Field(..., description="List of competitors to the company")
            
        tools = [
            OpenAIClient._create_tool(
                name="create_structured_data",
                description="Create structured business data from descriptive text",
                model=ComprehensiveExtractInput
            )
        ]
        
        system_prompt = "You are an AI that creates structured business data from descriptive text provided by users."
        content_prompt = f"""
        Create structured data for a business based on the following descriptive information:
        
        COMPANY NAME:
        {company_name}
        
        PRODUCTS DESCRIPTION:
        {products_description}
        
        TARGET PERSONAS DESCRIPTION:
        {personas_description}
        
        COMPETITORS DESCRIPTION:
        {competitors_description}
        
        Convert this information into structured data with the following components:
        
        1. COMPANY SUMMARY:
           Generate a concise but comprehensive summary explaining what {company_name} does, its main products/services, and target audience.
           Use all the provided information to create this summary.
        
        2. PRODUCTS/SERVICES:
           Create product or service entries with these attributes:
           - url: leave this blank
           - name: The official brand name of the product or service
           - description: A detailed, but concise description of the product or service
           - priority: A priority score from 1-10 (where 1 is lowest priority and 10 is highest)
        
        3. TARGET PERSONAS:
           Create target persona entries with these attributes:
           - name: A concise label for the target persona
           - description: A brief description of this target persona
           - priority: A priority score from 1-10 measuring how important this persona is to the company
        
        4. COMPETITORS:
           Create competitor entries with these attributes:
           - name: The official brand name of the competing company
           - description: A short description of what they do and how they relate to {company_name}
        """
        
        response = OpenAIClient._get_structured_completion(
            tools,
            "create_structured_data",
            system_prompt,
            content_prompt
        )
        
        return response


if __name__ == "__main__":
    import openai
    import json
    import certifi
    import os
    os.environ["SSL_CERT_FILE"] = certifi.where()
    
    # Example usage of the crawl-based function
    # with open("crawled_data.json", "r") as f:
    #     crawled_data = json.load(f)
    
    # all_data = OpenAIClient.extract_all_from_crawl(crawled_data)
    # json.dump(all_data, open("extracted_all_data.json", "w"), indent=4)
    
    # Example usage of the description-based function
    company_name = "Logitech G"
    
    products_desc = """
    Our company offers three main products:
    1. G402 Hyperion Fury FPS Gaming Mouse
    2. G903 LIGHTSPEED Wireless Gaming Mouse
    3. G305 LIGHTSPEED Wireless Gaming Mouse
    """
    
    personas_desc = """
    We target the following customer segments:
    - Hardcore Gamers
    - Casual Gamers
    - Professional Gamers
    """
    
    competitors_desc = """
    Our main competitors are:
    - Razer - Market leader with premium pricing
    - Corsair - Known for simplicity but lacks advanced features
    - SteelSeries - New entrant with innovative technology
    """
    
    structured_data = OpenAIClient.create_structured_data(products_desc, personas_desc, competitors_desc, company_name)
    json.dump(structured_data, open("created_structured_data.json", "w"), indent=4)
