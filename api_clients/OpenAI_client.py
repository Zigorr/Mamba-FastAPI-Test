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
        response = OpenAIClient._client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_prompt}
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": choice}}
        )
        return json.loads(response.choices[0].message.tool_calls[0].function.arguments)
    
    @staticmethod
    def get_personas_competitors(company_summary: str):
        class TargetPersona(BaseModel):
            name: str = Field(..., description="A concise label for the target persona.")
            description: str = Field(..., description="A very brief description of this target persona.")
            priority: int = Field(..., description="A priority score from 1-10 measuring the target persona's importance to the company.")

        class Competitor(BaseModel):
            name: str = Field(..., description="The official brand name of the competing company.")
            description: str = Field(..., description="A short description of the competitor and what they do.")

        class ExtractTargetPersonasInput(BaseModel):
            target_personas: List[TargetPersona]

        class ExtractCompetitorsInput(BaseModel):
            competitors: List[Competitor]

        tools = [
            OpenAIClient._create_tool(
                name="extract_target_personas",
                description="Extract target personas from company summary.",
                model=ExtractTargetPersonasInput
            ),
            OpenAIClient._create_tool(
                name="extract_competitors",
                description="Extract a list of competitors from a company summary.",
                model=ExtractCompetitorsInput
            )
        ]
        personas_system_prompt = "You are an AI that extracts target persona data."
        personas_prompt = f"""
            From the given company summary: --- {company_summary} ---
            Extract target persona data where:
            - name is a concise label for the target persona.
            - description is a very brief description of this target persona.
            - priority is a priority score from 1-10 measuring the target persona's importance to our company.
        """
        competitors_system_prompt = "You are an AI that extracts competitor data."
        competitors_prompt = f"""
        From the given company summary: --- {company_summary} ---
        Extract a list of competing companies where:
        - name is the official brand name of the competing company.
        - description is a short explanation of what they do and how they relate to our company.
        """
        response = {}
        response["target_personas"] = OpenAIClient._get_structured_completion(
            tools,
            "extract_target_personas",
            personas_system_prompt,
            personas_prompt
        )["target_personas"]
        response["competitors"] = OpenAIClient._get_structured_completion(
            tools,
            "extract_competitors",
            competitors_system_prompt,
            competitors_prompt
        )["competitors"]
        return response
    
    @staticmethod
    def get_products(crawled_data):
        """
        Extract products from crawled website data
        
        Args:
            crawled_data: A list of crawled webpage data containing URL and markdown content
            
        Returns:
            A dictionary containing a general company summary and a list of products
        """
        class Product(BaseModel):
            url: str = Field(..., description="The URL of the product or service page")
            name: str = Field(..., description="The official brand name of the product or service")
            description: str = Field(..., description="A detailed, but concise description of the product or service")
            priority: int = Field(..., description="A priority score from 1-10 (where 1 is lowest priority and 10 is highest)")

        class ExtractProductsInput(BaseModel):
            company_summary: str = Field(..., description="A concise summary of the company based on crawled data")
            products: List[Product]
            
        tools = [
            OpenAIClient._create_tool(
                name="extract_products",
                description="Extract products or services from crawled website data",
                model=ExtractProductsInput
            )
        ]
        
        # Prepare crawled data for prompt
        pages_data = []
        for page in crawled_data:
            # Limit markdown content to reduce token usage
            content_preview = page["markdown"][:1500] + "..." if len(page["markdown"]) > 1500 else page["markdown"]
            pages_data.append(f"URL: {page['url']}\nContent: {content_preview}")
        
        all_pages = "\n\n---\n\n".join(pages_data)
        
        system_prompt = "You are an AI that extracts product or service data from crawled website content."
        content_prompt = f"""
        From the given crawled website data, extract:
        
        1. A concise company summary explaining what the company does, its main products/services and target audience.
        
        2. Product or service information with the following attributes:
        - url: The URL of the product or service page
        - name: The official brand name of the product or service
        - description: A detailed, but concise description of the product or service
        - priority: A priority score from 1-10 (where 1 is lowest priority and 10 is highest)
          
        Only extract actual products (not categories or informational pages). 
        Prioritize products based on:
        - How prominently they appear in the data
        - Whether they have detailed specification information
        - Products with clear descriptions and pricing information
        
        Crawled Data:
        {all_pages}
        """
        
        response = OpenAIClient._get_structured_completion(
            tools,
            "extract_products",
            system_prompt,
            content_prompt
        )
        
        return response
        
    @staticmethod
    def extract_all_from_crawl(crawled_data):
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
            target_personas: List[TargetPersona] = Field(..., description="List of target personas for the company's products/services")
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
        for page in crawled_data:
            # Limit markdown content to reduce token usage
            content_preview = page["markdown"][:1500] + "..." if len(page["markdown"]) > 1500 else page["markdown"]
            pages_data.append(f"URL: {page['url']}\nContent: {content_preview}")
        
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


if __name__ == "__main__":
    import openai
    import json
    import certifi
    import os
    os.environ["SSL_CERT_FILE"] = certifi.where()
    
    # Example usage of the combined function
    with open("crawled_data.json", "r") as f:
        crawled_data = json.load(f)
    
    all_data = OpenAIClient.extract_all_from_crawl(crawled_data)
    json.dump(all_data, open("extracted_all_data.json", "w"), indent=4)
    
    # Individual function examples are commented out
    # Example for personas and competitors
    # summary = "Logitech G is a leading brand in gaming gear, offering a wide range of products including gaming mice, keyboards, headsets, and racing wheels designed for both casual and professional gamers. Their products are known for advanced technology, precision, and performance, catering to the needs of gamers worldwide."
    #response = OpenAIClient.get_personas_competitors(summary)
    #json.dump(response, open("extracted_personas_competitors.json", "w"), indent=4)
    
    # Example for product extraction
    #products = OpenAIClient.get_products(crawled_data)
    #json.dump(products, open("extracted_products.json", "w"), indent=4)
