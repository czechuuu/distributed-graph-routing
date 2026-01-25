# VM-optimized OSM PBF tiling (GCP)

This folder contains a faster tiling script for very large PBFs (e.g. Europe). It trades RAM for speed **but keeps RAM bounded** by extracting tiles in **batches** (one pass per batch) rather than one pass per tile.

## What’s different vs `scripts/tile_osm_fast.sh`

- **Old**: `osmium extract -b ...` per tile → re-reads the input file thousands of times for Europe (slow).
- **New**: `osmium extract -c batch.json` per *batch* → re-reads the input file tens of times (much faster).

Hard bounds:

- **`BATCH_TILES`**: maximum tiles per `osmium extract` pass (bounds memory / open outputs).
- **`MAX_PROCS`**: maximum concurrent extract passes (bounds CPU/IO/memory).


## Local usage

From repo root:

```bash
chmod +x tiling/tile_osm_vm.sh
OUTPUT_DIR=./osm_tiles_vm BATCH_TILES=128 MAX_PROCS=1 ./tiling/tile_osm_vm.sh europe
```

Upload to GCS (requires `gsutil`):

```bash
OUTPUT_DIR=./osm_tiles_vm BATCH_TILES=128 MAX_PROCS=2 ./tiling/tile_osm_vm.sh europe gs://rsp_graph_data_test/v2/osm_tiles
```

Note: when `gcs_path` is provided, the script **uploads and deletes each batch** (it does not keep all tiles locally).

## Deploy on Google Cloud (Compute Engine VM)

### Recommended setup

- **Machine type**: lots of vCPUs + RAM (e.g. `n2-standard-32` or larger)
- **Disk**: **200GB boot disk** is enough if you upload+delete each batch (bounded local storage)

### 1) Create a VM

Pick a zone close to Geofabrik and your GCS bucket, then run:

```bash
export PROJECT_ID="repetitive-shortest-paths"
export ZONE="us-central1-a"
export VM_NAME="osm-tiler"
export MACHINE="n2-standard-32"

gcloud compute instances create "$VM_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --machine-type="$MACHINE" \
  --boot-disk-size=200GB \
  --boot-disk-type=pd-balanced \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

Notes:

- `--scopes cloud-platform` allows `gsutil` uploads using the VM’s identity.

### 2) Install dependencies on the VM

SSH into the VM:

```bash
gcloud compute ssh "$VM_NAME" --zone="$ZONE"
```

These instructions assume **Debian/Ubuntu** as the VM image.

```bash
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  ca-certificates curl gnupg lsb-release \
  osmium-tool bc python3 coreutils jq git
```

If you want to **upload tiles to GCS** from the VM, install Google Cloud CLI (for `gsutil`):

```bash
if ! command -v gsutil >/dev/null 2>&1; then
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/cloud.google.gpg
  sudo chmod 0644 /etc/apt/keyrings/cloud.google.gpg
  echo "deb [signed-by=/etc/apt/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y google-cloud-cli
fi
```

### 3) Get the code onto the VM

Option A: clone the repo:

```bash
git clone https://github.com/<you>/<repo>.git
cd distributed-graph-routing
```

Option B: `gcloud compute scp` (from your laptop):

```bash
gcloud compute scp --recurse . "$VM_NAME:~/distributed-graph-routing" --zone="$ZONE"
```

### 4) Run tiling

On the VM:

```bash
cd ~/distributed-graph-routing
chmod +x tiling/tile_osm_vm.sh

export BUCKET="rsp_graph_data_test"
export TILES_PREFIX="v2/osm_tiles"

export OUTPUT_DIR="$HOME/osm_tiles_work"
export CACHE_DIR="$HOME/osm_pbf_cache"
export BATCH_TILES="64"
export MAX_PROCS="1"
export RAISE_NOFILE="65535"   # optional; helpful if you increase BATCH_TILES

./tiling/tile_osm_vm.sh europe "gs://$BUCKET/$TILES_PREFIX"
```

### 5) Clean up

Stop paying for the VM when done:

```bash
gcloud compute instances delete "$VM_NAME" --zone="$ZONE"
```

## Tuning tips (Europe)

- **Start conservative**:
  - `BATCH_TILES=128`
  - `MAX_PROCS=1` (increase to 2 if you have fast SSD and plenty of CPU)
- If you see “too many open files” errors:
  - lower `BATCH_TILES`, or set `RAISE_NOFILE=65535`
- If the VM is CPU-idle but disk isn’t maxed:
  - increase `MAX_PROCS` to 2–4
- If disk throughput is the bottleneck:
  - keep `MAX_PROCS` low; larger `MAX_PROCS` can make it slower due to IO contention
