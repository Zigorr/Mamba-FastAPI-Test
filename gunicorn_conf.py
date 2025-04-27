"""
Gunicorn configuration for production deployment with optimizations for large datasets.
"""

import multiprocessing
import os

# Server socket configuration
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
backlog = 2048

# Worker processes
# A generally accepted formula for web applications is (2 x CPU cores) + 1
workers = int(os.getenv("GUNICORN_WORKERS", (multiprocessing.cpu_count() * 2) + 1))
worker_class = "uvicorn.workers.UvicornWorker"  # Use Uvicorn's worker for ASGI support
worker_connections = 1000
timeout = 300  # Increased timeout for large operations
keepalive = 5
max_requests = 10000  # Restart workers after handling this many requests to prevent memory leaks
max_requests_jitter = 1000  # Add randomness to max_requests to prevent all workers from restarting at once

# Process naming
proc_name = "mamba_api"
pythonpath = "."

# Logging
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Server mechanics
daemon = False  # Don't daemonize in Docker containers
raw_env = []

# Server hooks
def on_starting(server):
    """Log when the server starts."""
    server.log.info("Starting Mamba FastAPI server")

def on_reload(server):
    """Log when the server reloads."""
    server.log.info("Reloading Mamba FastAPI server")

def post_fork(server, worker):
    """Actions to run after forking a worker."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def worker_int(worker):
    """Actions to run when a worker receives SIGINT."""
    worker.log.info(f"Worker {worker.pid} received INT signal")

def worker_abort(worker):
    """Actions to run when a worker is aborted."""
    worker.log.info(f"Worker {worker.pid} aborted")

def worker_exit(server, worker):
    """Actions to run when a worker exits."""
    server.log.info(f"Worker {worker.pid} exited")

# Performance optimizations
worker_tmp_dir = "/dev/shm"  # Use shared memory for temporary files
threads = int(os.getenv("GUNICORN_THREADS", 4))  # Number of threads per worker 