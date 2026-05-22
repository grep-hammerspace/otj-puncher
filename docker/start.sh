#!/usr/bin/env bash
set -eou pipefail

# Initialize CSV state file if missing
[ -f /app/otjs.csv ] || echo "date,time-spent,start-time,comments,posted" > /app/otjs.csv

# Start Tailscale daemon in userspace mode (required in containers)
tailscaled --tun=userspace-networking --socks5-server=localhost:1055 &

# Wait for daemon to be ready
sleep 2

# Join your tailnet
tailscale up \
  --authkey="${TAILSCALE_AUTHKEY}" \
  --hostname="hours-api"

echo "Tailscale connected"

exec python /app/otj_server.py