# GKE (zonal) tutorial for this repo

This is a *clean* "run these commands in order" guide based on commands that have worked in this project.

Assumptions from `k8s/` manifests:
- A GCS bucket contains `overlay_graph.pb` and `shard_graph.pb` files (see `cluster.md`).
- Pods use a mounted service-account JSON key at `/var/secrets/google/key.json` (K8s Secret `gcp-sa-key`).
- Images are pushed to Google Artifact Registry.

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

---

## 7) Build, push, and deploy (unified workflow)

This same workflow works for **both initial deploy and updates**. Run from repo root:

> ⚠️ **IMPORTANT**: You must **commit your changes** before deploying. The image tag is derived
> from the git commit SHA. If you have uncommitted changes:
> - The Docker image will contain your changes
> - But the tag will be the *old* commit SHA
> - Kubernetes won't detect a change and **won't trigger a rollout**
>
> Always commit first: `git add . && git commit -m "your message"`

```bash
# Set the image tag to the current git commit
TAG="$(git rev-parse --short HEAD)"

# Build images
docker build -f serving/Dockerfile.routing-api \
  -t "$REGION-docker.pkg.dev/$PROJECT/$REPO/routing-api:$TAG" .

docker build -f serving/Dockerfile.shard-worker \
  -t "$REGION-docker.pkg.dev/$PROJECT/$REPO/shard-worker:$TAG" .

# Push to Artifact Registry
docker push "$REGION-docker.pkg.dev/$PROJECT/$REPO/routing-api:$TAG"
docker push "$REGION-docker.pkg.dev/$PROJECT/$REPO/shard-worker:$TAG"

# Update kustomization.yaml with new image tags
cd k8s
kustomize edit set image \
  routing-api="$REGION-docker.pkg.dev/$PROJECT/$REPO/routing-api:$TAG" \
  shard-worker="$REGION-docker.pkg.dev/$PROJECT/$REPO/shard-worker:$TAG"

# Deploy to Kubernetes
kubectl apply -k .
```

> **How it works**: Kustomize rewrites the image references before applying. Since the tag
> changes with each commit, Kubernetes detects the spec change and performs a rolling update
> automatically—no manual restart needed.

## 8) Wait for rollout + get external endpoint

```bash
kubectl rollout status deploy/routing-api
kubectl rollout status deploy/shard-worker

kubectl get svc routing-api
```

## 9) Smoke test the public API

```bash
ROUTING_URL="http://<external-ip>"

curl -s -X POST "$ROUTING_URL/v1/route" \
  -H "Content-Type: application/json" \
  -d '{"start":{"lat":52.2297,"lng":21.0122},"end":{"lat":52.2400,"lng":21.0300}}'
```

---

## Updating with new code

When you modify the code and want to deploy updates, simply re-run **step 7**. The workflow is identical:

```bash
TAG="$(git rev-parse --short HEAD)"

# Build and push
docker build -f serving/Dockerfile.routing-api \
  -t "$REGION-docker.pkg.dev/$PROJECT/$REPO/routing-api:$TAG" .
docker build -f serving/Dockerfile.shard-worker \
  -t "$REGION-docker.pkg.dev/$PROJECT/$REPO/shard-worker:$TAG" .

docker push "$REGION-docker.pkg.dev/$PROJECT/$REPO/routing-api:$TAG"
docker push "$REGION-docker.pkg.dev/$PROJECT/$REPO/shard-worker:$TAG"

# Update image tags and deploy
cd k8s
kustomize edit set image \
  routing-api="$REGION-docker.pkg.dev/$PROJECT/$REPO/routing-api:$TAG" \
  shard-worker="$REGION-docker.pkg.dev/$PROJECT/$REPO/shard-worker:$TAG"

kubectl apply -k .

# Wait for rollout
kubectl rollout status deploy/routing-api deploy/shard-worker
```

### Rolling back

To rollback to a previous version:

```bash
# Option 1: Kubernetes native rollback (previous version)
kubectl rollout undo deploy/routing-api
kubectl rollout undo deploy/shard-worker

# Option 2: Deploy a specific older commit
git checkout <old-commit>
# Then run the build/push/deploy workflow above
```

---

## Debugging (if pods don't become Ready)

```bash
kubectl get pods -o wide
kubectl logs deploy/routing-api --tail=200
kubectl logs deploy/shard-worker --tail=200
kubectl describe pod -l app=routing-api
kubectl describe pod -l app=shard-worker
```

---

## Deleting the cluster (to avoid billing)

> **IMPORTANT**: GKE clusters incur charges for compute nodes, load balancer IPs, and persistent
> disks. Delete the cluster when not in use to avoid unexpected bills.

### Delete just the cluster (keeps Artifact Registry images)

```bash
gcloud container clusters delete "$CLUSTER" --zone "$ZONE" --quiet
```

This deletes:
- All nodes and pods
- The LoadBalancer external IP
- Associated compute resources

### Cost-saving alternative: Scale to zero nodes

If you want to keep the cluster configuration but stop paying for compute:

```bash
# Scale node pool to zero (stops compute charges, keeps cluster config)
gcloud container clusters resize "$CLUSTER" --zone "$ZONE" --num-nodes 0 --quiet

# Later, scale back up
gcloud container clusters resize "$CLUSTER" --zone "$ZONE" --num-nodes 2 --quiet
```

> **Note**: Even with zero nodes, you may still incur minimal charges for the cluster
> management fee (~$0.10/hour for standard clusters). For complete cost elimination,
> delete the cluster entirely.
