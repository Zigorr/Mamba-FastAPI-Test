FROM python:3.12.9

# Add build arguments for environment variables with defaults
ARG FIRECRAWL_API_KEY=""
ARG SECRET_KEY=""
ARG DATAFORSEO_LOGIN=""
ARG DATAFORSEO_PASSWORD=""
ARG DATABASE_URL=""
ARG OPENAI_API_KEY=""
ARG USE_MOCK_DATA="false"

# Set environment variables from build arguments
ENV FIRECRAWL_API_KEY=${FIRECRAWL_API_KEY}
ENV SECRET_KEY=${SECRET_KEY}
ENV DATAFORSEO_LOGIN=${DATAFORSEO_LOGIN}
ENV DATAFORSEO_PASSWORD=${DATAFORSEO_PASSWORD}
ENV DATABASE_URL=${DATABASE_URL}
ENV OPENAI_API_KEY=${OPENAI_API_KEY}
ENV USE_MOCK_DATA=${USE_MOCK_DATA}

WORKDIR /app

# Install system dependencies including PostgreSQL client
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 