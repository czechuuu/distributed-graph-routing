# GKE smoke test

## Apply manifests

```bash
kubectl apply -k k8s
```

## Wait for pods

```bash
kubectl rollout status deploy/routing-api
kubectl rollout status deploy/shard-worker
```

## Get public endpoint

```bash
kubectl get svc routing-api
```

## Smoke test

```bash
ROUTING_URL="http://<external-ip>"

curl -s -X POST "$ROUTING_URL/v1/route" \
  -H "Content-Type: application/json" \
  -d '{"start":{"lat":52.2297,"lng":21.0122},"end":{"lat":52.2400,"lng":21.0300}}'
```

Then expand returned segments:

```bash
curl -s -X POST "$ROUTING_URL/v1/route/expand" \
  -H "Content-Type: application/json" \
  -d '{"segments":[{"u":{"node_id":"8963866048","lat":52.22971,"lng":21.01218},"v":{"node_id":"8963866021","lat":52.22990,"lng":21.01280}}]}'
```
