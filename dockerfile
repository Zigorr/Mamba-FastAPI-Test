FROM python:3.12.9

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

# ADD THIS LINE: Copy the CA certificate
COPY ./ca-certificate.crt /app/ca-certificate.crt

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application using Gunicorn with Uvicorn workers
# The number of workers (--workers) can be tuned. A common recommendation is (2 * CPU_CORES) + 1.
# --preload loads application code before workers are forked, saving memory.
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "--workers", "2", "--bind", "0.0.0.0:8000", "--preload", "main:app"] 