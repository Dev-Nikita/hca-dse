#!/bin/sh
# Applies the link profile of this container, then starts the service.
if [ -n "$NETEM_DELAY" ]; then
  tc qdisc add dev eth0 root netem delay "${NETEM_DELAY}ms" rate "${NETEM_RATE}mbit" 2>/dev/null \
    || { echo "ERROR: link shaping failed" >&2; exit 1; }
fi
exec "$@"
