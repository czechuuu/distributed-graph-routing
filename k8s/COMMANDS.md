# GKE (zonal) tutorial for this repo

This is a *clean* “run these commands in order” guide based on commands that have worked in this project.

Assumptions from `k8s/` manifests:
- A GCS bucket contains `overlay_graph.pb` and `shard_graph.pb` files (see `cluster.md`).
- Pods use a mounted service-account JSON key at `/var/secrets/google/key.json` (K8s Secret `gcp-sa-key`).
- Deployments are updated to use images pushed to Artifact Registry.

## 0) Pick names / set variables

```bash
PROJECT=repetitive-shortest-paths
ZONE=us-central1-a
REGION=us-central1
CLUSTER=routing

BUCKET=rsp_graph_data_test
REPO=routing
```

## 1) Login + select project

```bash
gcloud auth login
gcloud config set project "$PROJECT"
```

## 2) Enable required APIs

```bash
gcloud services enable \
  container.googleapis.com \
  artifactregistry.googleapis.com
```

## 3) Create a **zonal** GKE cluster (fits smaller quotas)

```bash
gcloud container clusters create "$CLUSTER" \
  --zone "$ZONE" \
  --num-nodes 2 \
  --machine-type e2-standard-4 \
  --enable-ip-alias
```

Configure kubectl:

```bash
gcloud container clusters get-credentials "$CLUSTER" --zone "$ZONE"
kubectl get nodes
```

## 4) Create a service account for GCS reads + grant bucket permission

```bash
PROJECT="$(gcloud config get-value project)"
SA_NAME=routing-gcs
SA_EMAIL="$SA_NAME@$PROJECT.iam.gserviceaccount.com"

gcloud iam service-accounts create "$SA_NAME"
```

Grant bucket-level read permission:

```bash
gsutil iam ch "serviceAccount:${SA_EMAIL}:objectViewer" "gs://$BUCKET"
```

## 5) Create a JSON key and load it into Kubernetes as Secret `gcp-sa-key`

```bash
gcloud iam service-accounts keys create /tmp/key.json --iam-account "$SA_EMAIL"

kubectl create secret generic gcp-sa-key \
  --from-file=key.json=/tmp/key.json
```

Optional cleanup (recommended):

```bash
rm -f /tmp/key.json
```

## 6) Create Artifact Registry repo + configure Docker auth

```bash
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location "$REGION" || true

gcloud auth configure-docker "$REGION-docker.pkg.dev"
```

## 7) Build + push images (run from repo root)

```bash
TAG="$(git rev-parse --short HEAD)"

docker build -f serving/Dockerfile.routing-api \
  -t "$REGION-docker.pkg.dev/$PROJECT/$REPO/routing-api:$TAG" .

docker build -f serving/Dockerfile.shard-worker \
  -t "$REGION-docker.pkg.dev/$PROJECT/$REPO/shard-worker:$TAG" .

docker push "$REGION-docker.pkg.dev/$PROJECT/$REPO/routing-api:$TAG"
docker push "$REGION-docker.pkg.dev/$PROJECT/$REPO/shard-worker:$TAG"
```

## 8) Deploy Kubernetes manifests, then point Deployments at pushed images

```bash
kubectl apply -k k8s

kubectl set image deployment/routing-api \
  routing-api="$REGION-docker.pkg.dev/$PROJECT/$REPO/routing-api:$TAG"

kubectl set image deployment/shard-worker \
  shard-worker="$REGION-docker.pkg.dev/$PROJECT/$REPO/shard-worker:$TAG"
```

## 9) Wait for rollout + get external endpoint

```bash
kubectl rollout status deploy/routing-api
kubectl rollout status deploy/shard-worker

kubectl get svc routing-api
```

## 10) Smoke test the public API

```bash
ROUTING_URL="http://<external-ip>"

curl -s -X POST "$ROUTING_URL/v1/route" \
  -H "Content-Type: application/json" \
  -d '{"start":{"lat":52.2297,"lng":21.0122},"end":{"lat":52.2400,"lng":21.0300}}'
```

## Debugging (if pods don’t become Ready)

```bash
kubectl get pods -o wide
kubectl logs deploy/routing-api --tail=200
kubectl logs deploy/shard-worker --tail=200
kubectl describe pod -l app=routing-api
kubectl describe pod -l app=shard-worker
```
