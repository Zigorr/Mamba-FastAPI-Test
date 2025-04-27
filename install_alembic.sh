#!/bin/bash

# Install required packages
echo "Installing required packages..."
pip install alembic redis tenacity gunicorn uvloop

# Initialize the migrations
echo "Setting up migrations..."

# Apply the migration
echo "Applying database migration..."
alembic upgrade head

echo "Done! The database is now optimized for large datasets."
echo "Make sure Redis is running to enable caching features." 