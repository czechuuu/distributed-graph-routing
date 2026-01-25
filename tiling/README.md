# VM-optimized OSM PBF tiling (GCP)

This folder contains a tiling script optimized for very large PBFs (e.g. Europe). It produces **variable-sized tiles** by recursively splitting the filtered PBF based on file size.

## What’s different vs `scripts/tile_osm_fast.sh`

- **Old**: `osmium extract -b ...` per tile → re-reads the input file thousands of times for Europe (slow).
- **New**: recursive **supertile** extracts (via `osmium extract -c`) → variable-sized leaf tiles sized by `TARGET_LEAF_BYTES`.

Hard bounds:

- **`MAX_SPLIT_GRID_N`**: upper bound on grid size per split (caps children at `N×N`).
- **`TARGET_LEAF_BYTES`**: target size used to compute `N`.


## Local usage

From repo root:

```bash
chmod +x tiling/tile_osm_vm.sh
OUTPUT_DIR=./osm_tiles_vm SPLIT_GRID_N=auto TARGET_LEAF_BYTES=1073741824 ./tiling/tile_osm_vm.sh europe
```

Upload to GCS (requires `gsutil`):

```bash
OUTPUT_DIR=./osm_tiles_vm SPLIT_GRID_N=auto TARGET_LEAF_BYTES=1073741824 ./tiling/tile_osm_vm.sh europe gs://rsp_graph_data_test/v2/osm_tiles
```

Note: when `gcs_path` is provided, the script **uploads and deletes outputs** (it does not keep all tiles locally).

## Recursive split knobs

- `SPLIT_GRID_N=<int|auto>`: fixed grid size per level, or `auto` to choose `N` from size.
- `MIN_SPLIT_GRID_N=1`, `MAX_SPLIT_GRID_N=10`: bounds for auto mode.
- `TARGET_LEAF_BYTES=104857600`: auto mode target size per leaf PBF.
- `SUPERTILE_OVERLAP_KM=2.0`: overlap used when extracting child tiles (must be ≥ tile overlap).

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
export MACHINE="n2-highmem-16"

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

```bash
git clone https://github.com/czechuuu/distributed-graph-routing.git
cd distributed-graph-routing
```

### 4) Run tiling

On the VM:

```bash
cd ~/distributed-graph-routing
chmod +x tiling/tile_osm_vm.sh

export BUCKET="rsp_graph_data_massive"
export TILES_PREFIX="v3/osm_tiles"

export OUTPUT_DIR="$HOME/osm_tiles_work"
export CACHE_DIR="$HOME/osm_pbf_cache"
export SPLIT_GRID_N="auto"
export TARGET_LEAF_BYTES="1073741824"
export RAISE_NOFILE="65535"

./tiling/tile_osm_vm.sh europe "gs://$BUCKET/$TILES_PREFIX"
```

### 5) Clean up

Stop paying for the VM when done:

```bash
gcloud compute instances delete "$VM_NAME" --zone="$ZONE"
```

## Tuning tips (Europe)

- **Start conservative**:
  - `SPLIT_GRID_N=auto`
  - `TARGET_LEAF_BYTES=1073741824` (1 GiB)
- If you see “too many open files” errors:
  - lower `MAX_SPLIT_GRID_N`, or set `RAISE_NOFILE=65535`
