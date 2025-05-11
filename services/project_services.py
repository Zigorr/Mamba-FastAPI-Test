from api_clients import OpenAIClient, FireCrawlClient
import logging
logger = logging.getLogger(__name__)

def extract_project_data(project_url: str):
    # Get the company summary
    try:
        crawled_data = FireCrawlClient._crawl(project_url)
        company_data = OpenAIClient.extract_company_data(crawled_data)
    except Exception as e:
        logger.error(f"Error extracting project data: {e}")
        raise e;

    return company_data

def generate_project_data(
        project_name: str,
        products_description: str,
        personas_description: str,
        competitors_description: str
    ):
    try:
        # Get the project data
        company_data = OpenAIClient.generate_company_data(products_description, personas_description, competitors_description, project_name)
        return company_data
    except Exception as e:
        logger.error(f"Error generating project data: {e}")
        raise e;
