# Agency Manifesto: MambaSEOAgency

## Agency Description

This agency assists users with keyword research for their business.

## Mission Statement

To effectively gather business context from users via a custom interface and utilize this information to perform preliminary keyword research tasks.

## Operating Environment

-   The agency is deployed as a stateless microservice on a cloud-based backend server
-   It exposes a RESTful API that communicates with a React-based frontend application
-   The frontend makes HTTP requests to the agency's API endpoints for:
     - Submitting business information
     - Retrieving keyword research results
     - Managing research sessions
-   The agency processes requests asynchronously and returns structured JSON responses
-   All state management is handled by the frontend application
-   The agency maintains no persistent state between requests
-   Authentication and authorization are handled at the API gateway level
-   The system is designed for horizontal scaling to handle multiple concurrent users