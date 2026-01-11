This file contains commands that were run on the GCP to grant permissions.

1. Service account was created during a tutorial for Dataflow with python SDK i believe. The email is: 561773168964-compute@developer.gserviceaccount.com
2. I failed to grant permissions via the UI so i resorted to using gcloud commands on the console
 ```
 gcloud projects add-iam-policy-binding repetitive-shortest-paths \
    --member="serviceAccount:561773168964-compute@developer.gserviceaccount.com" \
    --role="roles/storage.objectAdmin"
 ```    
 ```
 gcloud projects add-iam-policy-binding repetitive-shortest-paths \
    --member="serviceAccount:561773168964-compute@developer.gserviceaccount.com" \
    --role="roles/dataflow.admin"
```
```
gcloud projects add-iam-policy-binding repetitive-shortest-paths \
    --member="serviceAccount:561773168964-compute@developer.gserviceaccount.com" \
    --role="roles/dataflow.worker"
```
```
gcloud projects add-iam-policy-binding repetitive-shortest-paths \
    --member="serviceAccount:561773168964-compute@developer.gserviceaccount.com" \
    --role="roles/bigquery.dataViewer"
```
```
gcloud projects add-iam-policy-binding repetitive-shortest-paths \
    --member="serviceAccount:561773168964-compute@developer.gserviceaccount.com" \
    --role="roles/bigquery.jobUser"
```
```
gcloud projects add-iam-policy-binding repetitive-shortest-paths \
    --member="serviceAccount:561773168964-compute@developer.gserviceaccount.com" \
    --role="roles/bigtable.user"
```
3. I created a bucket in the GCP console
    - make sure to clear the checkbox for block public access
    - make sure to select fine grained access
    - make sure to select the correct region
4. I created a BT instance with the following commands
```
# Create a BT instance - use only 1 node
gcloud bigtable instances create routing-instance \
    --display-name="Routing Instance" \
    --cluster-config=id=routing-cluster,zone=us-central1-a,nodes=1 \
    --instance-type=PRODUCTION

# 2. Configure 'cbt' to use your project and instance
echo project = repetitive-shortest-paths > ~/.cbtrc
echo instance = routing-instance >> ~/.cbtrc

# 3. Create the Tables
cbt createtable shortcuts
cbt createtable intra_edges

# 4. Create the Column Family 'cf' in BOTH tables
cbt createfamily shortcuts cf
cbt createfamily intra_edges cf
```
5. I added GCP permissions to build docker images and push them to gcr - it's usefule for the dataflow job so that when scaling the new workers don't need to build the dependencies.
```
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com
```
```
PROJECT=$(gcloud config get-value project)
NUM=$(gcloud projects describe $PROJECT --format='value(projectNumber)')

# Grant Cloud Build permission to act as Editor (simplest for prototyping)
gcloud projects add-iam-policy-binding $PROJECT \
    --member="serviceAccount:${NUM}@cloudbuild.gserviceaccount.com" \
    --role="roles/editor"
```
