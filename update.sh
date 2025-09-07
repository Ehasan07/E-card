#!/bin/bash

# This script automates the update process for the E-Card Creator project.

# Exit immediately if a command exits with a non-zero status.
set -e

# Navigate to the project directory
cd /var/www/ecard

# Pull the latest changes from the git repository
echo "Pulling latest changes..."
git pull

# Activate the virtual environment
source .venv/bin/activate

# Install or update python dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Restart the Gunicorn service to apply changes
echo "Restarting Gunicorn service..."
sudo systemctl restart ecard

# Reload Nginx to apply any changes
echo "Reloading Nginx..."
sudo systemctl reload nginx

echo "Update complete!"
