import sys
import os
from agency_swarm.tools import BaseTool
from pydantic import Field
import json
from datetime import datetime
# Add the project root to the Python path


from api_clients import DataForSEOClient
from api_clients import FireCrawlClient
import openai
import traceback

class ToFuListTool(BaseTool):
    """
    A tool that finds keywords for products using DataForSEO, focusing on Top-of-Funnel (ToFu) and Middle-of-Funnel (MoFu) intent.
    It takes product data from the project in shared state, determines the target language
    based on geo_market, generates ToFu/MoFu seed keywords, requests related keywords using DataForSEO,
    gathers keyword data (volume, difficulty, intent), then stores it in shared state.
    """

    def run(self):
        """
        Main execution method for the ToFuListTool.
        """

        project = self._shared_state.get('project')
        project_data = project.get('project_data')

        # Initialize keywords list for results
        keywords_list = []

        # Check if project data exists
        if not project:
            return "No project information found in shared state."

        # --- Determine Location and Language --- 
        target_location = project_data.get('geo_market', 'United States')
        target_language = DataForSEOClient.get_language_for_location(target_location)
        print(f"Using Location: '{target_location}', Language: '{target_language}' for API calls.")
        # --- End Determine Location and Language --- 

        # Get products/services Dictionary
        products = project_data.get('products')
        target_personas = project_data.get('personas')

        # Check if it's a List and not empty
        if not isinstance(products, list):
            return "'products' in project data is not a List."

        if not products:
             return "No products found in project data (List is empty)."

        # Initialize keywords by product dictionary
        keywords_by_product = {}

        # Process each product (row in the DataFrame)
        for index, product in enumerate(products):

            seeds = self._get_tofu_mofu_seeds(product, target_personas)

            product_name = product.get('name', '')
            if not product_name:
                 print(f"Skipping product at index {index} due to missing name.")
                 continue # Skip if name is missing

            print(f"Processing product: {product_name}")

            # Get keywords by product name using dynamic location/language
            try:
                product_keywords = DataForSEOClient.get_keywords_for_keywords(seeds, target_location, target_language)
                keywords_by_product[product_name] = product_keywords
            except Exception as e:
                print(f"Error getting keywords for {product_name}: {str(e)}")

        # If we have keywords, get keyword overview data in bulk
        if keywords_by_product:
            # Limit keywords per product to 500
            for product_name in keywords_by_product:
                if len(keywords_by_product[product_name]) > 500:
                    keywords_by_product[product_name] = keywords_by_product[product_name][:500]
                    print(f"Truncated keywords for {product_name} to 500.")

                try:
                    # Get keyword overview data in bulk using dynamic location/language
                    keyword_data = DataForSEOClient.get_keyword_overview(product_name, keywords_by_product[product_name], target_location, target_language)
                    keywords_list.extend(keyword_data)
                except Exception as e:
                    print(f"Error processing keyword overview data for {product_name}: {str(e)}")


        # Generate timestamp for filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        table_id = f"tofu_mofu_keywords_{timestamp}"

        # Create the final dictionary structure
        table_dict = {
            "id": table_id,
            "rows": keywords_list
        }

        # --- Save the results to shared state --- 
        # Check if the 'keywords_output' key exists in shared state
        if not self._shared_state.get('keywords_output'):
            # If it doesn't exist, create an empty dictionary
            self._shared_state.set('keywords_output', {})
        # Get the existing keywords_output dictionary
        keywords_output = self._shared_state.get('keywords_output')
        # Add the new table to the existing dictionary
        keywords_output[table_id] = table_dict
        # Update the shared state with the new dictionary
        self._shared_state.set('keywords_output', keywords_output)
        # --- End Save the results to shared state --- 

        keywords_ready = {
            "table": table_dict
        }
        action = {
            "action-type": "keywords_ready",
            "action-data": keywords_ready
        }
        self._shared_state.set('action', action)

        return f"Keywords table {table_id} has been saved to shared state."

    def _get_tofu_mofu_seeds(self, product, target_personas):
        """
        Internal method to get ToFu and MoFu seeds for a product.
        Agent is not allowed to call this method directly.
        """
        product_name = product.get('name', '')
        product_description = product.get('description', '')
        personas_markdown = "\n".join([f"**{persona.get('name', '')}**: {persona.get('description', '')}" for persona in target_personas])
        product_url_summary = None

        prompt = f"""
        # ROLE: SEO Keyword Strategist (ToFu/MoFu Specialist)

        # CONTEXT:
        You are an expert SEO Keyword Strategist specializing in identifying informational and consideration-stage keywords (Top-of-Funnel [ToFu] and Middle-of-Funnel [MoFu]). You excel at understanding a target persona's problems, questions, and research process related to a specific offering.

        # INPUT:
        You will receive the following information:
        1.  **Offering Name:** The official name.
        2.  **Offering Description:** Key features, benefits, problems solved, location, etc.
        3.  **Target Personas:** Core needs, pain points, goals, and questions related to the offering.
        4.  **Offering URL Page Summary (if available):** Summary of the offering's primary URL content.

        # TASK:
        Your objective is to generate a list of precisely 10 "world-class" quality seed keywords based *primarily* on the provided Description, Persona, and URL Summary. These keywords should reflect how the target persona might search when they are:
        *   **Aware of a problem** the offering solves (ToFu).
        *   **Researching potential solutions** or understanding the topic area (ToFu/MoFu).
        *   **Comparing different approaches** or types of solutions (MoFu).
        *   **Learning about the benefits** or use cases of the offering type (MoFu).

        These keywords must meet the following strict criteria:

        1.  **Problem/Solution Focus:** Reflect the core problems the offering addresses or the general type of solution it represents.
        2.  **Informational & Consideration Intent:** Indicate a searcher looking for information, understanding, comparisons, or education (e.g., "how to [solve problem]", "[problem] symptoms", "[solution type] benefits", "[category] comparison", "what is [concept]", "[offering type] for [industry]").
        3.  **High Relevance:** Highly relevant to the *problems*, *benefits*, or *category* associated with the described offering. Accurately represent the *space* this offering operates in. Avoid overly broad terms but don't be exclusively product-specific unless using comparison terms.
        4.  **Persona Alignment:** Reflect plausible search queries the *target persona* would use during their awareness and consideration phases.
        5.  **Conciseness:** Keywords should generally be 2-5 words long. Aim for natural language queries.

        # OUTPUT REQUIREMENTS:
        - Your response **must** be a list of exactly 10 keywords.
        - The keywords **must** be comma-separated.
        - **Do not** include numbers, bullet points, explanations, introductory text, or any text other than the 10 comma-separated keywords.

        # EXAMPLE (Illustrative - Adapt based on actual input):
        For a B2B SaaS tool for project management: "improve team collaboration", "project management software benefits", "best tools for remote teams", "how to track project progress", "[Competitor A] vs [Competitor B]", "what is Agile workflow", "reduce project delays", "collaboration tool comparison", "task management tips", "software for [industry] project management"

        --- PRODUCT INFO ---
        Product Name: {product_name}
        Product Description: {product_description}
        Target Personas: {personas_markdown}
        {f"Product URL Page Summary: {product_url_summary}" if product_url_summary else "(No URL summary available)"}
        ---
        """
        try:
            # Generate seed keywords with OpenAI
            client = openai.OpenAI()

            response = client.chat.completions.create(
                model="gpt-4o-2024-08-06",
                messages=[
                    {"role": "system", "content": "You are an expert SEO Keyword Strategist. Your task is to generate exactly 10 Top-of-Funnel (ToFu) and Middle-of-Funnel (MoFu) keywords based on the offering information provided. Focus on the Offering Description, Target Persona (problems, questions, goals), and URL Summary to create keywords reflecting informational and consideration-stage searches. Keywords should represent problems, solutions, benefits, comparisons, or educational queries relevant to the offering's space. Strictly output ONLY the 10 keywords, comma-separated, with no other text."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.2 # Slightly higher temperature for broader ideas
            )
            keywords_string = response.choices[0].message.content
            keywords = [k.strip() for k in keywords_string.split(",") if k.strip()]
            # Ensure exactly 10 keywords, padding if necessary
            if len(keywords) < 10:
                print(f"Warning: OpenAI generated only {len(keywords)} keywords for {product_name}. Padding with generic terms.")
                # Pad with more generic but related terms if possible, fallback to product name
                generic_padding = [f"what is {product_name}", f"{product_name} benefits", f"how does {product_name} work"]
                needed = 10 - len(keywords)
                padding = (generic_padding + [product_name] * needed)[:needed] # Combine and take needed amount
                keywords.extend(padding)
            return keywords[:10]
        except Exception as e:
            print(f"Error calling OpenAI API: {e}") # Keep concise error message
            print("--- Full Traceback ---")
            traceback.print_exc() # Print the detailed traceback
            print("---------------------")
            # Return default on error, ensuring 10 elements (more generic fallback)
            return [f"what is {product_name}", f"{product_name} benefits", f"{product_name} alternatives", f"{product_name} features", f"learn about {product_name}", f"compare {product_name}", f"{product_name} use cases", f"{product_name} guide", f"{product_name} review", product_name]

if __name__ == "__main__":
    import glob

    tool = ToFuListTool()

    # Mock project data structure
    mock_project = {
        'name': 'Test Project',
        'website_url': 'http://example.com',
        'project_data': {
            'products': [
                {
                    'name': 'Mock Product',
                    'url': '',
                    'description': 'A product for testing.',
                    'priority': 5
                }
            ],
            'personas': [
                {
                    'name': 'Mock Persona',
                    'description': 'A test persona for this product.',
                    'priority': 10
                }
            ],
            'competitors': [
                {
                    'name': 'Mock Competitor',
                    'description': 'A competitor in the market'
                }
            ],
            'geo_market': 'United States'
        }
    }
    
    tool._shared_state.set('project', mock_project)

    # Run the tool
    response = tool.run()
    print(f"\nTool Run Response:\n{response}")
