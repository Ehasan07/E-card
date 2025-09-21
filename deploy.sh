#!/bin/bash

# This script is for deploying the V-card project (repository name: E-card) on a fresh Ubuntu server.
# Run this script as a user with sudo privileges.

# --- Variables ---
HETZNER_IP="91.99.167.26"
DOMAIN="ecard.dupno.com"
GIT_REPO="https://github.com/Ehasan07/E-card"
PROJECT_DIR="/home/user/ecard"
USER="user"
DB_NAME="ecard_db"
DB_USER="ecard_user"
DB_PASS="your_strong_password" # CHANGE THIS!

# --- Update and Install Packages ---
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y nginx python3-venv git postgresql postgresql-contrib libpq-dev

# --- Setup Database ---
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME;"
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -c "ALTER ROLE $DB_USER SET client_encoding TO 'utf8';"
sudo -u postgres psql -c "ALTER ROLE $DB_USER SET default_transaction_isolation TO 'read committed';"
sudo -u postgres psql -c "ALTER ROLE $DB_USER SET timezone TO 'UTC';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

# --- Setup Project ---
# Create a non-root user to run the application
sudo adduser $USER

# Create project directory
sudo mkdir -p $PROJECT_DIR
sudo chown -R $USER:$USER $PROJECT_DIR

# Clone the project
git clone $GIT_REPO $PROJECT_DIR

# Create virtual environment and install dependencies
cd $PROJECT_DIR
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cat > .env << EOL
SECRET_KEY='$(openssl rand -hex 32)'
DEBUG=False
ALLOWED_HOSTS=$DOMAIN,$HETZNER_IP
DATABASE_URL='postgres://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME'
EOL

# Run Django commands
python manage.py collectstatic --noinput
python manage.py migrate

# --- Configure Nginx ---
sudo cp $PROJECT_DIR/nginx.conf /etc/nginx/sites-available/ecard
sudo ln -s /etc/nginx/sites-available/ecard /etc/nginx/sites-enabled/
sudo nginx -t # Test Nginx configuration
sudo systemctl restart nginx

# --- Configure Gunicorn with Systemd ---
sudo cp $PROJECT_DIR/gunicorn.service /etc/systemd/system/
sudo cp $PROJECT_DIR/gunicorn.socket /etc/systemd/system/

sudo systemctl start gunicorn.socket
sudo systemctl enable gunicorn.socket
sudo systemctl status gunicorn.socket

# --- Configure Firewall ---
sudo ufw allow 'Nginx Full'
sudo ufw allow OpenSSH
sudo ufw enable

# --- Final Instructions ---
echo "-----------------------------------------------------"
echo "Deployment script finished!"
echo ""
echo "Next steps:"
echo "1. Point your domain's DNS A record to $HETZNER_IP."
echo "2. Once DNS has propagated, run certbot to get an SSL certificate:"
echo "   sudo apt-get install certbot python3-certbot-nginx"
echo "   sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
echo "-----------------------------------------------------"
