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
    if ! pgrep -x munged >/dev/null 2>&1; then
        rm -f /run/munge/munge.socket.2
        runuser -u munge -- /usr/sbin/munged
    fi
}

prepare_benchmark_dirs() {
    mkdir -p \
        /archive/demo_user \
        /episode/work \
        /scratch/demo_user/classifier \
        /scratch/demo_user/cutouts \
        /scratch/demo_user/lightcurve-fit \
        /scratch/demo_user/mhd \
        /scratch/demo_user/nbody \
        /scratch/demo_user/photoz \
        /scratch/demo_user/rv-sweep
    chown -R demo_user:demo_user \
        /archive/demo_user \
        /episode \
        /scratch/demo_user
}

prepare_codex_config() {
    local model="${CODEX_MODEL:-gpt-5.6-terra}"

    case "${model}" in
        *[!A-Za-z0-9._-]*)
            echo "Invalid CODEX_MODEL value: ${model}" >&2
            exit 1
            ;;
    esac

    install -d -o demo_user -g demo_user -m 0700 /home/demo_user/.codex
    printf 'model = "%s"\n' "${model}" > /home/demo_user/.codex/config.toml
    chown demo_user:demo_user /home/demo_user/.codex/config.toml
    chmod 0600 /home/demo_user/.codex/config.toml
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
        | grep -Fqx "${expected}"
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
        exec runuser -u slurm -- /usr/sbin/slurmdbd -Dvv
        ;;

    register-cluster)
        start_munge
        wait_for_port slurmdbd 6819 "slurmdbd"

        cluster_name="${CLUSTER_NAME:-scc}"
        account_name="${ACCOUNT_NAME:-proj_astro}"
        benchmark_user="${BENCHMARK_USER:-demo_user}"

        if accounting_row_exists cluster "${cluster_name}" format=Cluster; then
            echo "Slurm cluster ${cluster_name} is already registered."
        else
            sacctmgr --immediate add cluster name="${cluster_name}"
        fi

        if ! accounting_row_exists account "${account_name}" \
            where "name=${account_name}" format=Account; then
            sacctmgr --immediate add account \
                name="${account_name}" \
                cluster="${cluster_name}" \
                description="Synthetic benchmark allocation" \
                organization=synthetic
        fi

        if ! accounting_row_exists association \
            "${benchmark_user}|${account_name}|${cluster_name}" \
            where "user=${benchmark_user}" "account=${account_name}" \
            "cluster=${cluster_name}" format=User,Account,Cluster; then
            sacctmgr --immediate add user \
                name="${benchmark_user}" \
                account="${account_name}" \
                cluster="${cluster_name}"
        fi
        ;;

    slurmctld)
        start_munge
        wait_for_port slurmdbd 6819 "slurmdbd"
        exec runuser -u slurm -- /usr/sbin/slurmctld -Dvv
        ;;

    login)
        start_munge
        prepare_benchmark_dirs
        prepare_codex_config
        wait_for_port slurmctld 6817 "slurmctld"
        exec /usr/sbin/sshd -D -e
        ;;

    slurmd)
        start_munge
        prepare_benchmark_dirs
        wait_for_port slurmctld 6817 "slurmctld"
        exec /usr/sbin/slurmd -Dvv
        ;;

    *)
        exec "$@"
        ;;
esac
