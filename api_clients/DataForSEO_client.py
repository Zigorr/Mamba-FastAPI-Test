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
    
    def __init__(self):
        #load_dotenv()
        self.login = os.getenv("DATAFORSEO_LOGIN")
        self.password = os.getenv("DATAFORSEO_PASSWORD")
        if not self.login or not self.password:
            raise ValueError("DataForSEO login and password must be set in .env file")
        self.domain = "api.dataforseo.com"

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


    @staticmethod
    def _get_client():
        """Initializes and returns the RestClient."""
        if not DataForSEOClient._login or not DataForSEOClient._password:
            raise ValueError("DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD must be set in environment variables.")
        return RestClient(DataForSEOClient._login, DataForSEOClient._password)

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
        client = DataForSEOClient._get_client()
        response = {}
        try:
            response = client.post(endpoint, post_data)
        except Exception as e:
            print(f"Error calling DataForSEO {endpoint}: {e}")
            response = {"status_code": 50000, "status_message": f"Client error: {e}", "tasks": [], "tasks_count": 0, "tasks_error": 1}
        finally:
            return response

    @staticmethod
    def locations_and_languages():
        endpoint = "/v3/dataforseo_labs/locations_and_languages"
        client = DataForSEOClient._get_client()
        response = {}
        try:
            response = client.get(endpoint)
        except Exception as e:
            print(f"Error calling DataForSEO {endpoint}: {e}")
            response = {"status_code": 50000, "status_message": f"Client error: {e}", "tasks": [], "tasks_count": 0, "tasks_error": 1}
        finally:
            return response
    
    @staticmethod
    def _parse_locations_languages(response):
        locations_dict = {}
        for location in response['tasks'][0]['result']:
            if location['available_languages']:
                locations_dict[location['location_name']] = location['available_languages'][0]['language_name']
        return locations_dict
    
    @staticmethod
    def _validate_location(location_name, locations_dict):
        if location_name in locations_dict:
            return location_name
        return "United States"
    
    @staticmethod
    def get_language_for_location(location_name):
        response = DataForSEOClient.locations_and_languages()
        locations_dict = DataForSEOClient._parse_locations_languages(response)
        location_name = DataForSEOClient._validate_location(location_name, locations_dict)
        return locations_dict[location_name]
    
    @staticmethod
    def get_keywords_for_keywords(keywords, location_name, language_name):
        post_data = [{
            "location_name": location_name,
            "language_name": language_name,
            "keywords": keywords
        }]

        response = DataForSEOClient.keywords_for_keywords_live(post_data)
        keywords = [result['keyword'] 
            for task in response['tasks'] 
            for result in task.get('result', []) 
            if 'keyword' in result]
        return keywords
    
    @staticmethod
    def get_keyword_overview(product_name, keywords, location_name, language_name):
        task_data = dict()
        task_data[len(task_data)] = {
            "keywords": keywords,
            "location_name": location_name,
            "language_name": language_name,
        }
        keyword_data = DataForSEOClient.keyword_overview_live(task_data)
        results = []
        for task in keyword_data['tasks']:
            if task['result'][0].get('items') and len(task['result'][0]['items']) > 0:
                for item in task['result'][0]['items']:
                    keyword = item.get('keyword')
                    keyword_info = item.get('keyword_info', {})
                    keyword_props = item.get('keyword_properties', {})
                    search_intent = item.get('search_intent_info', {})

                    search_volume = keyword_info.get('search_volume') if keyword_info.get('search_volume') is not None else 0
                    difficulty = keyword_props.get('keyword_difficulty') if keyword_props.get('keyword_difficulty') is not None else 0
                    intent = search_intent.get('main_intent') if search_intent.get('main_intent') is not None else 'unknown'

                    if keyword:
                        results.append({
                            'product': product_name,
                            'keyword': keyword,
                            'search_volume': search_volume,
                            'difficulty': difficulty,
                            'intent': intent
                        })
        return results


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