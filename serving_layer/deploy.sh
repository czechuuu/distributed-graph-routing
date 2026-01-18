#!/bin/bash
# Infrastructure initialization script

PROJECT_ID=$(gcloud config get-value project)
INSTANCE_NAME="routing-backend"
ZONE="us-central1-c"

# Create Compute Engine instance
gcloud compute instances create $INSTANCE_NAME \
    --project=$PROJECT_ID \
    --zone=$ZONE \
    --machine-type=e2-medium \
    --tags=http-server \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --scopes=https://www.googleapis.com/auth/cloud-platform

# Wait for SSH to be available
echo "Waiting for SSH to become available..."
until gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command="true" --quiet 2>/dev/null; do
    echo "Instance is not ready yet. Retrying in 2 seconds..."
    sleep 2
done

# Archive project files and transfer to VM
# Create distribution directory structure
rm -rf dist
mkdir -p dist/serving_layer
cp *.py dist/serving_layer/
cp -r storage_types dist/serving_layer/
cp vm_deploy.sh dist/
# Ensure __init__.py exists
touch dist/serving_layer/__init__.py

# Create tarball
tar -czf project.tar.gz -C dist .
rm -rf dist

gcloud compute scp project.tar.gz $INSTANCE_NAME:~/ --zone=$ZONE
gcloud compute scp vm_deploy.sh $INSTANCE_NAME:~/ --zone=$ZONE

# Execute deployment on VM
echo "Executing remote deployment..."
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command="chmod +x vm_deploy.sh && ./vm_deploy.sh routing-assets-repetitive routing-instance"

# Cleanup
echo "Cleaning up local artifacts..."
rm project.tar.gz