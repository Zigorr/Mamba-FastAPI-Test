@echo off
setlocal enabledelayedexpansion

REM Set environment variables if not already set
if "%DATABASE_URL%"=="" set DATABASE_URL=postgresql://postgres:postgres@localhost:5432/mamba
if "%SECRET_KEY%"=="" set SECRET_KEY=secret-key-for-jwt-please-change-in-production
if "%REDIS_URL%"=="" set REDIS_URL=redis://localhost:6379/0
if "%CACHE_FORMAT%"=="" set CACHE_FORMAT=orjson
if "%ENVIRONMENT%"=="" set ENVIRONMENT=production

REM Apply database migrations if needed
echo Applying database migrations...
call alembic upgrade head

REM Start server with optimized settings
echo Starting Mamba FastAPI server...

if "%ENVIRONMENT%"=="development" (
    echo Running in development mode with auto-reload
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
) else (
    echo Running in production mode
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
)

endlocal 