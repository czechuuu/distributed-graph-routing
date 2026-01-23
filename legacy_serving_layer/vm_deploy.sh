#!/bin/bash
# Deployment script executed on the remote VM

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <BUCKET_NAME> <BIGTABLE_INSTANCE_ID>"
    exit 1
fi

BUCKET_NAME=$1
INSTANCE_ID=$2
PROJECT_ID=$(gcloud config get-value project)

# Install system dependencies
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip tar

# Extract project files
tar -xzf ~/project.tar.gz

# Create virtual environment
python3.11 -m venv ~/venv
source ~/venv/bin/activate

# Install python dependencies
pip install --upgrade pip
if [ -f "serving_layer/requirements.txt" ]; then
    pip install -r serving_layer/requirements.txt
else
    pip install fastapi uvicorn google-cloud-bigtable networkx ujson
fi

# Configure systemd service for the application
sudo bash -c "cat <<EOF > /etc/systemd/system/routing-backend.service
[Unit]
Description=FastAPI Routing Backend
After=network.target

[Service]
User=$USER
WorkingDirectory=$HOME
Environment=\"PYTHONPATH=$HOME\"
Environment=\"PROJECT_ID=$PROJECT_ID\"
Environment=\"INSTANCE_ID=$INSTANCE_ID\"
ExecStart=$HOME/venv/bin/python3 -m uvicorn serving_layer.app:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF"

# Reload systemd and start service
sudo systemctl daemon-reload
sudo systemctl enable routing-backend
sudo systemctl restart routing-backend