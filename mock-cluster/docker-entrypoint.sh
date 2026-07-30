#!/usr/bin/env bash
set -euo pipefail

mkdir -p \
    /run/munge \
    /run/sshd \
    /var/lib/slurm \
    /var/lib/slurmd \
    /var/log/slurm \
    /var/run/slurmctld \
    /var/run/slurmd \
    /var/run/slurmdbd \
    /var/spool/slurmctld \
    /var/spool/slurmd

chown -R munge:munge /run/munge
chown -R slurm:slurm \
    /etc/slurm \
    /var/lib/slurm \
    /var/log/slurm \
    /var/run/slurmctld \
    /var/run/slurmdbd \
    /var/spool/slurmctld
chmod 0600 /etc/slurm/slurmdbd.conf

start_munge() {
    if [ ! -S /run/munge/munge.socket.2 ]; then
        gosu munge /usr/sbin/munged
    fi
}

wait_for_port() {
    local host="$1"
    local port="$2"
    local description="$3"

    echo "Waiting for ${description} at ${host}:${port} ..."
    until timeout 1 bash -c "2>/dev/null >/dev/tcp/${host}/${port}"; do
        sleep 2
    done
}

accounting_row_exists() {
    local entity="$1"
    local expected="$2"
    shift 2

    sacctmgr --noheader --parsable2 show "${entity}" "$@" \
        | grep -Fqx "${expected}|"
}

case "${1:-}" in
    slurmdbd)
        start_munge
        echo "Waiting for the accounting database ..."
        until mariadb \
            --host=mysql \
            --user=slurm \
            --password=password \
            --execute="SELECT 1" >/dev/null 2>&1; do
            sleep 2
        done
        exec gosu slurm /usr/sbin/slurmdbd -Dvv
        ;;

    register-cluster)
        start_munge
        wait_for_port slurmdbd 6819 "slurmdbd"

        cluster_name="${CLUSTER_NAME:-linux}"
        account_name="${ACCOUNT_NAME:-local}"

        if accounting_row_exists cluster "${cluster_name}" format=Cluster; then
            echo "Slurm cluster ${cluster_name} is already registered."
        else
            sacctmgr --immediate add cluster name="${cluster_name}"
        fi

        if ! accounting_row_exists account "${account_name}" \
            where "name=${account_name}" "cluster=${cluster_name}" format=Account; then
            sacctmgr --immediate add account \
                name="${account_name}" \
                cluster="${cluster_name}" \
                description="Local testing" \
                organization=local
        fi

        if ! accounting_row_exists user submitter \
            where name=submitter "account=${account_name}" \
            "cluster=${cluster_name}" format=User; then
            sacctmgr --immediate add user \
                name=submitter \
                account="${account_name}" \
                cluster="${cluster_name}"
        fi
        ;;

    slurmctld)
        start_munge
        wait_for_port slurmdbd 6819 "slurmdbd"
        exec gosu slurm /usr/sbin/slurmctld -Dvv
        ;;

    login)
        start_munge
        wait_for_port slurmctld 6817 "slurmctld"
        exec /usr/sbin/sshd -D -e
        ;;

    slurmd)
        start_munge
        wait_for_port slurmctld 6817 "slurmctld"
        exec /usr/sbin/slurmd -Dvv
        ;;

    *)
        exec "$@"
        ;;
esac
