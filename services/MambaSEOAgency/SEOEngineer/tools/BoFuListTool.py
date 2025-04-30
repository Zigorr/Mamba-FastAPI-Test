import sys
import os
from agency_swarm.tools import BaseTool
from pydantic import Field
import json
import pandas as pd
from datetime import datetime
# Add the project root to the Python path


from api_clients import DataForSEOClient
from api_clients import FireCrawlClient
import openai
import traceback

class BoFuListTool(BaseTool):
    """
    A tool that finds keywords for products using DataForSEO.
    It takes brand information and product data from shared state, determines the target language
    based on market_geo, requests related keywords, gathers keyword data, then stores it in shared state.
    """

    def run(self):
        """
        Main execution method for the BoFuListTool.
        """

        data = self._shared_state.get('business_info_data')

        # Initialize keywords list for results
        keywords_list = []

        # Check if business data exists
        if not data:
            return "No business information found in shared state."

        # --- Determine Location and Language --- 
        target_location = data.get('market_geo', 'United States')
        target_language = DataForSEOClient.get_language_for_location(target_location)
        print(f"Using Location: '{target_location}', Language: '{target_language}' for API calls.")
        # --- End Determine Location and Language --- 

        # Get products/services Dictionary
        products = data.get('products_services')

        # Check if it's a List and not empty
        if not isinstance(products, list):
            return "'products_services' in shared state is not a List."

        if not products:
             return "No products or services found in business information (List is empty)."



        # Initialize keywords by product dictionary
        keywords_by_product = {}

        # Process each product (row in the DataFrame)
        for index, product in enumerate(products):

            seeds = self._get_bofu_seeds(product)

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
        table_id = f"bofu_keywords_{timestamp}"

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


    def _get_bofu_seeds(self, product):
        """
        Internal method to get BoFu seeds for a product.
        Agent is not allowed to call this method directly.
        """
        product_name = product.get('name', '')
        product_description = product.get('description', '')
        product_target_persona = product.get('target_persona')
        #product_url = product.get('url', '')
        product_url_summary = product.get('url_summary', '')

        # if product_url:
        #     # Only try to get the summary if a URL exists
        #     try:
        #         product_url_summary = FireCrawlClient.extract_product_url_summary(product_url)
        #     except Exception as e:
        #         print(f"Error calling FireCrawlClient: {e}")
        #         product_url_summary = None # Ensure it's None on error

        prompt = f"""
        # ROLE: SEO Keyword Strategist (BoFu Specialist)

        # CONTEXT:
        You are an expert SEO Keyword Strategist specializing in identifying high-intent, bottom-of-funnel (BoFu) keywords. You excel at understanding a specific offering and generating highly concise, direct search terms that signal purchase readiness.

        # INPUT:
        You will receive the following information:
        1.  **Offering Name:** The official name.
        2.  **Offering Description:** Key features, benefits, unique value proposition, location, etc.
        3.  **Target Persona:** Core needs and goals related to the offering.
        4.  **Offering URL Page Summary (if available):** Summary of the offering's primary URL content.

        # TASK:
        Your objective is to generate a list of precisely 10 "world-class" quality keywords based *primarily* on the provided Description, Persona, and URL Summary. Keywords **must be extremely direct and concise**, reflecting how the target persona might search when seriously considering this specific offering. **Strongly prioritize brevity (2-3 words preferred)** while maintaining high relevance.

        These keywords must meet the following strict criteria:

        1.  **Deep Offering Understanding:** Reflect key, specific attributes or benefits from the description/URL summary.
        2.  **Bottom-of-Funnel (BoFu) Intent:** Strongly indicate commercial/transactional intent or final research stages (e.g., terms for pricing, specific configurations, comparisons, reviews, availability, essential features).
        3.  **High Relevance & Specificity:** Highly relevant to the *attributes* of the described offering. Accurately represent *this specific offering*. Avoid generics.
        4.  **Persona Alignment:** Reflect plausible, concise search queries the *target persona* would use in final decision stages.
        5.  **Extreme Conciseness:** Keywords MUST contain **no more than 4 words**. **Ideal keywords are 2-3 words long.** Achieve maximum conciseness without losing critical specificity.

        # OUTPUT REQUIREMENTS:
        - Your response **must** be a list of exactly 10 keywords.
        - The keywords **must** be comma-separated.
        - **Do not** include numbers, bullet points, explanations, introductory text, or any text other than the 10 comma-separated keywords.

        # EXAMPLE (Illustrative - Adapt based on actual input, aiming for brevity):
        For a B2B SaaS tool: "[Feature] pricing", "[Pain Point] tool", "[Competitor] alternative", "[Integration] tool", "[Benefit] review", "implement [Category]", "enterprise [Category]", "[Use Case] software", "compare [Category]", "secure [Industry] platform"

        --- PRODUCT INFO ---
        Product Name: {product_name}
        Product Description: {product_description}
        Product Target Persona: {product_target_persona}
        {f"Product URL Page Summary: {product_url_summary}" if product_url_summary else "(No URL summary available)"}
        ---
        """
        try:
            # Generate seed keywords with OpenAI
            client = openai.OpenAI()

            response = client.chat.completions.create(
                model="gpt-4o-2024-08-06",
                messages=[
                    {"role": "system", "content": "You are an expert SEO Keyword Strategist. Your task is to generate exactly 10 high-intent, Bottom-of-Funnel (BoFu) keywords based on the offering information provided in the user message. Focus primarily on the Offering Description, Target Persona, and URL Summary to create keywords that accurately represent the offering's specific attributes and value proposition. Keywords should reflect plausible search queries from the target persona in their final decision stage. While the Offering Name provides context, keywords don't need to include it explicitly but must be highly relevant. Strictly output ONLY the 10 keywords, comma-separated, with no other text."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.1  # Slightly lower temperature for more consistent brand voice
            )
            keywords_string = response.choices[0].message.content
            keywords = [k.strip() for k in keywords_string.split(",") if k.strip()]
            # Ensure exactly 10 keywords, padding if necessary (though unlikely with good prompt)
            if len(keywords) < 10:
                print(f"Warning: OpenAI generated only {len(keywords)} keywords for {product_name}. Padding with product name.")
                keywords.extend([product_name] * (10 - len(keywords)))
            return keywords[:10]
        except Exception as e:
            print(f"Error calling OpenAI API: {e}") # Keep concise error message
            print("--- Full Traceback ---")
            traceback.print_exc() # Print the detailed traceback
            print("---------------------")
            return [product_name] * 10 # Return default on error, ensuring 10 elements

if __name__ == "__main__":
    import glob

    tool = BoFuListTool()

    # --- Mocking shared_state for local testing ---
    class MockSharedState:
        def __init__(self):
            self._state = {}
        def set(self, key, value):
            print(f"[MockSharedState] Setting key '{key}'")
            self._state[key] = value
        def get(self, key, default=None):
            return self._state.get(key, default)
        def get_all(self):
            return self._state.copy()
    tool._shared_state = MockSharedState() # Assign mock directly
    # --- End Mocking ---

    # Find the most recent business form data
    business_form_files = glob.glob("../../business_form/*/data.json") # Adjust path relative to tool location
    if business_form_files:
        latest_file = max(business_form_files, key=os.path.getmtime)
        try:
            with open(latest_file, 'r') as f:
                business_data = json.load(f)
                # Convert products_services to DataFrame for the mock state
                if 'products_services' in business_data and isinstance(business_data['products_services'], list):
                    business_data['products_services'] = pd.DataFrame(business_data['products_services'])
                tool._shared_state.set('business_info_data', business_data) # Use the mock set method
                print(f"Loaded business data from {latest_file} into mock shared state.")
        except Exception as e:
            print(f"Error loading business data for testing: {str(e)}")
    else:
        print("No business form data found for testing. Using default mock data.")
        # Provide default mock data if no file found
        mock_business_data = {
            'company_name': 'Test Co',
            'website': 'http://example.com',
            'niche': 'Testing',
            'location': 'United States',
            'target_personas': 'Testers',
            'market_geo': 'United States', # Default for mock
            'value_props': 'Great tests',
            'products_services': pd.DataFrame([{
                'name': 'Mock Product',
                'url': '',
                'description': 'A product for mocking.',
                'target_persona': 'Mock users',
                'priority': '5'
            }])
        }
        tool._shared_state.set('business_info_data', mock_business_data)

    # Run the tool
    response = tool.run()
    print(f"\nTool Run Response:\n{response}")

    # Print the resulting DataFrame from mock shared state
    final_df = tool._shared_state.get('bofu_keywords')
    if isinstance(final_df, pd.DataFrame):
        print("\nGenerated Keywords DataFrame (from mock shared state):")
        print(final_df.to_string())
    else:
        print("\nNo keywords DataFrame found in mock shared state.")
