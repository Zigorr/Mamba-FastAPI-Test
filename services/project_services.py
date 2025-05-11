from api_clients import OpenAIClient, FireCrawlClient

from repositories import ProjectRepository

def extract_project_data(project_url: str):
    # Get the company summary
    company_data = FireCrawlClient.extract_products_from_website(project_url)

    # Get the target personas and competitors
    personas_competitors = OpenAIClient.get_personas_competitors(company_data['company_summary'])

    # Get the products
    project_data = {
        'products': company_data['products'],
        'company_summary': company_data['company_summary'],
        'personas': personas_competitors['target_personas'],
        'competitors': personas_competitors['competitors']
    }
    return project_data
