#!/bin/bash
# Runs the API and the worker together; if either exits, the container exits and Docker restarts it.
set -e
uvicorn customer_intelligence.main:app --host 0.0.0.0 --port 8000 --proxy-headers \
  --forwarded-allow-ips='*' &
python -m customer_intelligence.worker &
wait -n
exit 1
