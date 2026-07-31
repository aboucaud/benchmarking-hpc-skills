#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
    observer)
        install -d -o root -g root -m 0700 /observer
        if ! pgrep -x munged >/dev/null 2>&1; then
            rm -f /run/munge/munge.socket.2
            runuser -u munge -- /usr/sbin/munged
        fi
        exec /usr/bin/python3 /opt/mock-cluster/observer_service.py
        ;;
    gateway)
        install -d -o root -g root -m 0700 /observer
        exec /usr/bin/python3 /opt/mock-cluster/credential_gateway.py
        ;;
    ssh-forwarder)
        exec /usr/bin/python3 /opt/mock-cluster/ssh_forwarder.py
        ;;
    *)
        echo "usage: support-entrypoint.sh observer|gateway|ssh-forwarder" >&2
        exit 2
        ;;
esac
