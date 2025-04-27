@echo off
echo Installing required packages for database optimizations...

REM Install the required packages
pip install alembic redis tenacity httpx orjson ujson msgpack cachetools pymemcache

REM Initialize and apply the migrations
echo Setting up database migrations...
alembic upgrade head

echo.
echo Done! The database is now optimized for large datasets.
echo Make sure Redis is running to enable caching features.
echo.
echo You can start the server with: start_server.bat 