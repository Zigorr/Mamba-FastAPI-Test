# Install with pip install firecrawl-py
from pydantic import BaseModel, Field
from typing import Any, Optional, List
from dotenv import load_dotenv
import logging
import openai
import os
import json

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


if __name__ == "__main__":
    import openai
    import json
    import certifi
    import os
    os.environ["SSL_CERT_FILE"] = certifi.where()
    summary = "Logitech G is a leading brand in gaming gear, offering a wide range of products including gaming mice, keyboards, headsets, and racing wheels designed for both casual and professional gamers. Their products are known for advanced technology, precision, and performance, catering to the needs of gamers worldwide."
    response = OpenAIClient.get_personas_competitors(summary)
    json.dump(response, open("extracted_personas_competitors.json", "w"), indent=4)
