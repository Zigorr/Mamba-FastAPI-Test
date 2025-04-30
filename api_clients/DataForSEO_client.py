import os
from dotenv import load_dotenv
import json
from datetime import datetime
from http.client import HTTPSConnection
from base64 import b64encode
from json import loads
from json import dumps
import openai
from urllib.parse import urlparse
import base64

load_dotenv(override=True)


class RestClient:
    domain = "api.dataforseo.com"

    def __init__(self, username, password):
        self.username = username
        self.password = password

    def request(self, path, method, data=None):
        connection = HTTPSConnection(self.domain)
        try:
            base64_bytes = b64encode(
                ("%s:%s" % (self.username, self.password)).encode("ascii")
                ).decode("ascii")
            headers = {'Authorization' : 'Basic %s' %  base64_bytes, 'Content-Encoding' : 'gzip'}
            connection.request(method, path, headers=headers, body=data)
            response = connection.getresponse()
            return loads(response.read().decode())
        finally:
            connection.close()

    def get(self, path):
        return self.request(path, 'GET')

    def post(self, path, data):
        if isinstance(data, str):
            data_str = data
        else:
            data_str = dumps(data)
        return self.request(path, 'POST', data_str)

class DataForSEOClient:
    """
    A static class to interact with the DataForSEO API.
    Handles authentication and provides methods for specific endpoints.
    Automatically saves responses to a structured directory.
    """
    
    _login = os.getenv("DATAFORSEO_LOGIN")
    _password = os.getenv("DATAFORSEO_PASSWORD")
    _responses_base_dir = "responses" # Base directory for saving responses
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    mock_keywords_for_keywords_path = os.path.join(
        project_root,
        "responses/v3_keywords_data_google_ads_keywords_for_keywords_live/req_20250419_133603_740885/full_response.json"
    )
    mock_keyword_overview_path = os.path.join(
        project_root,
        "responses/v3_dataforseo_labs_google_keyword_overview_live/req_20250419_133616_257292/full_response.json"
    )
    
    def __init__(self):
        #load_dotenv()
        self.login = os.getenv("DATAFORSEO_LOGIN")
        self.password = os.getenv("DATAFORSEO_PASSWORD")
        if not self.login or not self.password:
            raise ValueError("DataForSEO login and password must be set in .env file")
        self.domain = "api.dataforseo.com"
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        # Define mock file paths relative to project root
        self.mock_keywords_for_keywords_path = os.path.join(
            self.project_root,
            "responses/v3_keywords_data_google_ads_keywords_for_keywords_live/req_20250419_133603_740885/full_response.json"
        )
        self.mock_keyword_overview_path = os.path.join(
            self.project_root,
            "responses/v3_dataforseo_labs_google_keyword_overview_live/req_20250419_133616_257292/full_response.json"
        )

    def _request(self, path, method, data=None):
        base64_bytes = base64.b64encode(f"{self.login}:{self.password}".encode("ascii")).decode("ascii")
        headers = {
            'Authorization': 'Basic %s' % base64_bytes,
            'Content-Encoding': 'gzip',
            'Content-Type': 'application/json'
        }
        conn = HTTPSConnection(self.domain)
        try:
            conn.request(method, path, headers=headers, body=data)
            response = conn.getresponse()
            return json.loads(response.read().decode())
        finally:
            conn.close()

    def _save_response(self, response_data, endpoint_path, request_id):
        dir_path = os.path.join(self.project_root, "responses", endpoint_path, request_id)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, "full_response.json")
        try:
            with open(file_path, 'w') as f:
                json.dump(response_data, f, indent=4)
            print(f"Saved DataForSEO response to {file_path}")
        except Exception as e:
            print(f"Error saving DataForSEO response to {file_path}: {e}")

    @staticmethod
    def _get_client():
        """Initializes and returns the RestClient."""
        if not DataForSEOClient._login or not DataForSEOClient._password:
            raise ValueError("DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD must be set in environment variables.")
        return RestClient(DataForSEOClient._login, DataForSEOClient._password)

    @staticmethod
    def _save_response(endpoint, response):
        """Saves the API response to a structured directory."""
        try:
            # Generate a unique ID using timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            request_id = f"req_{timestamp}" 
            
            # Sanitize endpoint path for directory name
            endpoint_name = endpoint.strip("/").replace("/", "_") 
            
            # Create the full path for saving (using class attribute for base dir)
            save_dir = os.path.join(DataForSEOClient.project_root, DataForSEOClient._responses_base_dir, endpoint_name, request_id)
            os.makedirs(save_dir, exist_ok=True) # Create directories if they don't exist
            
            filepath = os.path.join(save_dir, "full_response.json")
            
            # Write the response to the file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(response, f, indent=2, ensure_ascii=False)
            print(f"Saved DataForSEO response to {filepath}")
        except Exception as e:
            print(f"Error saving DataForSEO response: {e}")

    @staticmethod
    def search_volume_live(post_data):
        """
        Makes a request to the /v3/keywords_data/google_ads/search_volume/live endpoint.
        Saves the response automatically.
        
        Args:
            post_data (list): The payload for the API request.
            
        Returns:
            dict: The API response.
        """
        client = DataForSEOClient._get_client()
        endpoint = "/v3/keywords_data/google_ads/search_volume/live"
        response = {} # Initialize response dictionary
        try:
            # Make the API call
            response = client.post(endpoint, post_data)
        except Exception as e:
            # Handle exceptions during the API call
            print(f"Error calling DataForSEO {endpoint}: {e}")
            # Create a standard error structure to be saved and returned
            response = {
                "status_code": 50000, 
                "status_message": f"Client error: {e}",
                "tasks": [],
                "tasks_count": 0,
                "tasks_error": 1
            }
        finally:
            # Ensure the response (or error structure) is always saved
            DataForSEOClient._save_response(endpoint, response)
            return response # Return the response (or error structure)


    @staticmethod
    def keywords_for_site_live(post_data):
        """
        Makes a request to the /v3/keywords_data/google_ads/keywords_for_site/live endpoint.
        Saves the response automatically.
        
        Args:
            post_data (list): The payload for the API request.
            
        Returns:
            dict: The API response.
        """
        client = DataForSEOClient._get_client()
        endpoint = "/v3/keywords_data/google_ads/keywords_for_site/live"
        response = {}
        try:
            response = client.post(endpoint, post_data)
        except Exception as e:
            print(f"Error calling DataForSEO {endpoint}: {e}")
            # Create a standard error structure to be saved and returned
            response = {
                "status_code": 50000, 
                "status_message": f"Client error: {e}",
                "tasks": [],
                "tasks_count": 0,
                "tasks_error": 1
            }
        finally:
            # Ensure the response (or error structure) is always saved
            DataForSEOClient._save_response(endpoint, response)
            return response # Return the response (or error structure)


    @staticmethod
    def keyword_overview_live(post_data):
        """
        Makes a request to the /v3/dataforseo_labs/google/keyword_overview/live endpoint.
        Saves the response automatically.
        
        Args:
            post_data (list): The payload for the API request.
            
        Returns:
            dict: The API response.
        """
        client = DataForSEOClient._get_client()
        endpoint = "/v3/dataforseo_labs/google/keyword_overview/live"
        response = {}
        try:
            response = client.post(endpoint, post_data)
        except Exception as e:
            print(f"Error calling DataForSEO {endpoint}: {e}")
            # Create a standard error structure to be saved and returned
            response = {
                "status_code": 50000, 
                "status_message": f"Client error: {e}",
                "tasks": [],
                "tasks_count": 0,
                "tasks_error": 1
            }   
        finally:
            # Ensure the response (or error structure) is always saved
            DataForSEOClient._save_response(endpoint, response)
            return response # Return the response (or error structure)
    
    @staticmethod
    def keywords_for_keywords_live(post_data):
        """
        Makes a request to the /v3/keywords_data/google_ads/keywords_for_keywords/live endpoint.
        Saves the response automatically.
        
        Args:
            post_data (list): The payload for the API request.
            
        Returns:
            dict: The API response.
        """
        endpoint = "/v3/keywords_data/google_ads/keywords_for_keywords/live"
        # --- Mock Data Check --- 
        if os.getenv("USE_MOCK_DATA", "False").lower() == "true":
            print(f"--- MOCK MODE: Loading data from {DataForSEOClient.mock_keywords_for_keywords_path} ---")
            try:
                with open(DataForSEOClient.mock_keywords_for_keywords_path, 'r') as f:
                    mock_data = json.load(f)
                    return mock_data
            except FileNotFoundError:
                print(f"Error: Mock file not found at {DataForSEOClient.mock_keywords_for_keywords_path}. ABORTING (in mock mode).")
                return {"error": "Mock file not found", "path": DataForSEOClient.mock_keywords_for_keywords_path}
            except Exception as e:
                print(f"Error loading mock data: {e}. ABORTING (in mock mode).")
                return {"error": f"Error loading mock data: {e}"}
        # --- End Mock Data Check ---
        
        client = DataForSEOClient._get_client()
        response = {}
        try:
            response = client.post(endpoint, post_data)
        except Exception as e:
            print(f"Error calling DataForSEO {endpoint}: {e}")
            response = {"status_code": 50000, "status_message": f"Client error: {e}", "tasks": [], "tasks_count": 0, "tasks_error": 1}
        finally:    
            DataForSEOClient._save_response(endpoint, response)
            return response

    @staticmethod
    def keywords_for_url_live(post_data):
        """
        Generates seed keywords for a given product URL using OpenAI.
        Makes a request to the /v3/keywords_data/google_ads/keywords_for_keywords/live endpoint.
        Saves the response automatically.
        
        Args:
            post_data (dict): The payload for the API request.
            
        Returns:
            dict: The API response.
        """
        url = post_data["target"]
        domain = urlparse(url).netloc.split(".")[1]
        product_page = urlparse(url).path.split("/")[-1]
        product_page = product_page.split(".")[0]
        product_keyword = domain + " " + product_page.replace("-", " ").replace("_", " ")

        prompt = f"""Product URL: {url}
        You will generate 3 seed keywords that are describe the product with high accuracy.
        Keywords must include the model-specific product name and the brand name.
        Your response should be a list of keywords separated by commas."""
            
        try:
            # Generate seed keywords with OpenAI
            client = openai.OpenAI()

            response = client.chat.completions.create(
                model="gpt-4o-2024-08-06",
                messages=[
                    {"role": "system", "content": "You are an expert who specializes in finding keywords for a given product. You will be given a product URL and you will need to find seed keywords that are relevant to the product."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.1  # Slightly lower temperature for more consistent brand voice
            )
            keywords = response.choices[0].message.content.split(",")
            # Clean up and filter keywords
            cleaned_keywords = []
            for keyword in keywords:
                # Strip whitespace and remove any empty strings
                keyword = keyword.strip()
                if keyword:
                    # Filter to ensure keywords contain the domain name (brand)
                    if domain.lower() in keyword.lower():
                        cleaned_keywords.append(keyword)
            
            # If we filtered out too many keywords, use the original list
            if len(cleaned_keywords) < 1 and len(keywords) > 0:
                print(f"Warning: Too few keywords ({len(cleaned_keywords)}) contain the domain '{domain}'. Using original keywords.")
                cleaned_keywords = [k.strip() for k in keywords if k.strip()]
            
            # Update the keywords list with the filtered version
            keywords = cleaned_keywords[:3]
        except Exception as e:
            print(f"Error calling OpenAI: {e}")

        # Get the domain from the product URL


        final_post_data = [{
            "location_name": post_data["location_name"],
            "language_name": post_data["language_name"],
            "keywords": keywords
        }]
        return DataForSEOClient.keywords_for_keywords_live(final_post_data)

if __name__ == "__main__":
    # Example usage (requires environment variables DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD)

    keywords_by_product = {
        "corsair k95": ["corsair k95"],
        "logitech g502": ["logitech g502"],
        }
    post_data = dict()
    # simple way to set a task
    post_data[len(post_data)] = dict(
        location_name="United States",
        language_name="English",
        keywords=keywords_by_product["corsair k95"]
    )

    print("Testing keywords_for_keywords_live...")
    response = DataForSEOClient.keyword_overview_live(post_data)
    print("\nAPI Call Complete. Response received and saved (check 'responses' folder).")
    # Optional: print response to console for immediate feedback
    # print(json.dumps(response, indent=2)) 