#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "login" ]]; then
    install -d -o root -g root -m 0700 /run/site-monitor
    /usr/bin/python3 /usr/local/libexec/site-process-monitor &
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
