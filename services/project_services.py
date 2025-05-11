from api_clients import OpenAIClient, FireCrawlClient

from repositories import ProjectRepository

def extract_project_data(project_url: str):
    # Get the company summary
    crawled_data = FireCrawlClient._crawl(project_url)
    company_data = OpenAIClient.extract_all_from_crawl(crawled_data)

    return company_data
