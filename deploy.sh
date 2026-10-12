#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
namespace="${NAMESPACE:-workshop-s21}"
echo "Deploying Afterplay into $namespace"
kubectl -n "$namespace" get service vllm >/dev/null
kubectl -n "$namespace" create configmap afterplay-code \
  --from-file=app.py --from-file=game.py --from-file=index.html \
  --from-file=app.js --from-file=style.css \
  --dry-run=client -o yaml | kubectl -n "$namespace" apply -f -
kubectl -n "$namespace" apply -f k8s.yaml
kubectl -n "$namespace" rollout restart deployment/afterplay
kubectl -n "$namespace" rollout status deployment/afterplay --timeout=180s
echo "Ready. On your laptop: kubectl --kubeconfig s21.yaml -n $namespace port-forward svc/afterplay 8080:8080"
