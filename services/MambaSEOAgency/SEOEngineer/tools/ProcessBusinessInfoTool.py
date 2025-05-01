# ProcessBusinessInfoTool.py

from agency_swarm.tools import BaseTool
from pydantic import Field

from dotenv import load_dotenv


from api_clients import FireCrawlClient


class ProcessBusinessInfoTool(BaseTool):
    """
    Retrieves the business information from the shared state. and processes it.
    """
    def run(self):
        """
        Retrieves the business information from the shared state and processes it.
        Modifies the business information with url_summary and sorts the products by priority.
        Stores the processed business information in the shared state.
        Stores client context as markdown in the shared state.
        """
        try:
            business_info_data = self._shared_state.get('business_info_data')
            if business_info_data is None:
                return "Error: No business information found in shared state."
        except Exception as e:
            return f"Error: Could not retrieve business information from shared state: {e}"
        
        try:
            for product in business_info_data['products_services']:
                if 'url' in product and product['url']:
                    product['url_summary'] = FireCrawlClient.extract_product_url_summary(product['url'])
                else:
                    product['url_summary'] = ""
        except Exception as e:
            return f"Error: Could not extract product url summary: {e}"
        
        try:
            # sort products by priority
            business_info_data['products_services'] = sorted(business_info_data['products_services'], key=lambda x: x['priority'], reverse=True)
        except Exception as e:
            return f"Error: Could not sort products by priority: {e}"
        
        try:
            # store the processed data in the shared state
            self._shared_state.set('business_info_data', business_info_data)
            self._shared_state.set('client_context', self._convert_business_info_to_markdown(business_info_data))
            self._shared_state.set('action', None)
            return "Successfully processed business information."
        except Exception as e:
            return f"Error: Could not store processed business information in shared state: {e}"
    
    def _convert_business_info_to_markdown(self, business_info):
        """
        Internal function to convert business info to markdown and store it in shared state.
        Should not be directly called by agent.

        Args:
            business_info (dict): Dictionary containing business information
            
        Returns:
            str: Markdown formatted string of the business information
        """
        markdown = f"# {business_info['company_name']}\n\n"

        # Basic business information
        markdown += "## Business Overview\n"
        markdown += f"- **Location:** {business_info['location']}\n"
        markdown += f"- **Market Geography:** {business_info['market_geo']}\n"
        markdown += f"- **Niche:** {business_info['niche']}\n"
        markdown += f"- **Website:** {business_info['website']}\n\n"

        # Value propositions
        markdown += "## Value Propositions\n"
        value_props = business_info['value_props']

        markdown += f"{value_props}\n\n"

        # Target personas
        markdown += "## Target Personas\n"
        markdown += f"{business_info['target_personas']}\n\n"

        # Products and services
        markdown += "## Products & Services\n"

        for product in business_info['products_services']:
            markdown += f"### {product['name']} (Priority: {product['priority']})\n"
            markdown += f"- **Description:** {product['description']}\n"
            markdown += f"- **Target Persona:** {product['target_persona']}\n"
            if 'url' in product and product['url']:
                markdown += f"- **URL:** {product['url']}\n"
            else:
                markdown += f"- **URL:** None\n"
            if 'url_summary' in product and product['url_summary']:
                markdown += f"- **URL Summary:** {product['url_summary']}\n"
            else:
                markdown += f"- **URL Summary:** None\n"
            markdown += "\n"
        
        print("Client context stored in shared state under key 'client_context'")
        return markdown

# Basic test case
if __name__ == "__main__":
    load_dotenv(override=True)

    tool = ProcessBusinessInfoTool()
    # Inject the mock shared_state into the tool instance for testing
    business_info_data = {
        "company_name": "Logitech",
        "location": "United States",
        "market_geo": "United States",
        "niche": "computer electronics",
        "products_services": [
            {
                "description": "mouse",
                "name": "Logitech G402 Hyperion Fury",
                "priority": "8",
                "target_persona": "gamers",
                "url": "https://www.logitechg.com/en-nz/products/gaming-mice/g402-hyperion-fury-fps-gaming-mouse.html"
            },
            {
                "description": "high end mouse",
                "name": "Logitech G402 Hyperion Fury",
                "priority": "9",
                "target_persona": "gamers",
                "url": ""
            }
        ],
        "target_personas": "gamers",
        "value_props": "high performance gaming",
        "website": "https://www.logitech.com/en-us"
    }
    tool._shared_state.set('business_info_data', business_info_data)
    # --- End Mocking --- 

    result = tool.run()
    print("Tool Result:")
    # The tool now returns a string message on success or error
    print(result)

    if result == "Successfully processed business information.":
        print("Client context stored in shared state under key 'client_context'")
        print(tool._shared_state.get('client_context'))
