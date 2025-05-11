from agency_swarm.tools import BaseTool

class RetrieveClientContextTool(BaseTool):
    """
    A tool to retrieve the client context from the shared state.
    If client context doesn't exist, it generates it from the project data.
    """
    def run(self):
        """
        Main execution method for the RetrieveClientContextTool.
        Retrieves the client context from the shared state and returns it.
        If no client context exists, it creates one from project data.
        """
        print("Retrieving client context...")
        client_context = self._shared_state.get('client_context', None)
        
        if client_context:
            return client_context
        else:
            # Generate context from project data
            project = self._shared_state.get('project')
            if not project:
                return "No project data or client context found."
                
            return self._generate_context_from_project(project)
    
    def _generate_context_from_project(self, project):
        """
        Internal method to generate client context from project data.
        Agent is not allowed to call this method directly.
        
        Args:
            project (dict): Project data from shared state
            
        Returns:
            str: Markdown formatted string of the project information
        """
        project_data = project.get('project_data', {})
        
        markdown = f"# {project.get('name', 'Project')}\n\n"

        # Basic project information
        markdown += "## Project Overview\n"
        markdown += f"- **Website:** {project.get('website_url', 'N/A')}\n"
        markdown += f"- **Market Geography:** {project_data.get('geo_market', 'N/A')}\n\n"

        # Company summary if available
        if project_data.get('company_summary'):
            markdown += "## Company Summary\n"
            markdown += f"{project_data.get('company_summary')}\n\n"

        # Products
        if project_data.get('products'):
            markdown += "## Products\n"
            for product in project_data.get('products', []):
                priority = product.get('priority', 'N/A')
                markdown += f"### {product.get('name', 'Unnamed Product')} (Priority: {priority})\n"
                markdown += f"- **Description:** {product.get('description', 'No description')}\n"
                if product.get('url'):
                    markdown += f"- **URL:** {product.get('url')}\n"
                markdown += "\n"

        # Personas
        if project_data.get('personas'):
            markdown += "## Target Personas\n"
            for persona in project_data.get('personas', []):
                priority = persona.get('priority', 'N/A')
                markdown += f"### {persona.get('name', 'Unnamed Persona')} (Priority: {priority})\n"
                markdown += f"- **Description:** {persona.get('description', 'No description')}\n\n"

        # Competitors
        if project_data.get('competitors'):
            markdown += "## Competitors\n"
            for competitor in project_data.get('competitors', []):
                markdown += f"### {competitor.get('name', 'Unnamed Competitor')}\n"
                markdown += f"- **Description:** {competitor.get('description', 'No description')}\n\n"
        
        # Store the generated context for future use
        self._shared_state.set('client_context', markdown)
        
        return markdown

