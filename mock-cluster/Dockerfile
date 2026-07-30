FROM rockylinux:9

LABEL org.opencontainers.image.source="https://github.com/aboucaud/benchmarking-hpc-skills" \
      org.opencontainers.image.title="mock-slurm-cluster" \
      org.opencontainers.image.description="Laptop-sized Slurm cluster for benchmark testing"

RUN set -eux \
    && dnf -y makecache \
    && dnf -y install dnf-plugins-core \
    && dnf config-manager --set-enabled crb \
    && dnf -y install \
        bash-completion \
        dbus-devel \
        gcc \
        gcc-c++ \
        git \
        hostname \
        http-parser-devel \
        hwloc \
        hwloc-devel \
        iproute \
        json-c-devel \
        kernel-headers \
        libbpf-devel \
        make \
        mariadb \
        mariadb-devel \
        munge \
        munge-devel \
        nodejs \
        npm \
        openssh-server \
        perl \
        python3 \
        procps-ng \
        psmisc \
        systemd-devel \
        util-linux \
    && dnf clean all \
    && rm -rf /var/cache/dnf

RUN set -eux \
    && useradd --uid 5001 --create-home --shell /bin/bash demo_user \
    && echo "demo_user:demo_user" | chpasswd \
    && ssh-keygen -A \
    && mkdir -p /run/sshd \
    && { \
        echo "# Local test cluster only"; \
        echo "PasswordAuthentication yes"; \
        echo "UsePAM no"; \
        echo "PermitRootLogin no"; \
    } > /etc/ssh/sshd_config.d/50-mock-slurm.conf

COPY demo-user.bashrc /home/demo_user/.bashrc
RUN chown demo_user:demo_user /home/demo_user/.bashrc \
    && chmod 0644 /home/demo_user/.bashrc

ARG SLURM_TAG=slurm-25-11-2-1
ARG CODEX_VERSION=0.146.0
ARG BUILD_JOBS=2

RUN npm install --global "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force

RUN set -eux \
    && git clone --branch "${SLURM_TAG}" --single-branch --depth=1 \
        https://github.com/SchedMD/slurm.git /tmp/slurm \
    && cd /tmp/slurm \
    && ./configure \
        --enable-debug \
        --prefix=/usr \
        --sysconfdir=/etc/slurm \
        --libdir=/usr/lib64 \
        --with-mysql_config=/usr/bin \
    && make -j"${BUILD_JOBS}" \
    && make install \
    && install -D -m0644 etc/cgroup.conf.example /etc/slurm/cgroup.conf.example \
    && install -D -m0644 etc/slurm.conf.example /etc/slurm/slurm.conf.example \
    && install -D -m0644 etc/slurmdbd.conf.example /etc/slurm/slurmdbd.conf.example \
    && install -D -m0644 contribs/slurm_completion_help/slurm_completion.sh \
        /etc/profile.d/slurm_completion.sh \
    && sed -i '1iif ! [[ $- == *i* ]]; then return; fi' \
        /etc/profile.d/slurm_completion.sh \
    && rm -rf /tmp/slurm \
    && groupadd --system --gid 990 slurm \
    && useradd --system --gid slurm --uid 990 slurm

RUN set -eux \
    && mkdir -p \
        /archive/demo_user \
        /data \
        /episode/work \
        /etc/mock-slurm \
        /etc/slurm \
        /run/munge \
        /scratch/demo_user \
        /var/lib/slurm \
        /var/lib/slurmd \
        /var/log/slurm \
        /var/run/slurmctld \
        /var/run/slurmd \
        /var/run/slurmdbd \
        /var/spool/slurmctld \
        /var/spool/slurmd \
    && chown -R demo_user:demo_user \
        /archive/demo_user \
        /data \
        /episode \
        /scratch/demo_user \
    && chown -R munge:munge /run/munge \
    && chown -R slurm:slurm \
        /var/lib/slurm \
        /var/log/slurm \
        /var/run/slurmctld \
        /var/run/slurmdbd \
        /var/spool/slurmctld \
    && /sbin/create-munge-key

COPY slurm.conf /etc/slurm/slurm.conf
COPY gres.conf /etc/slurm/gres.conf
COPY slurmdbd.conf /etc/slurm/slurmdbd.conf
COPY cgroup.conf /etc/slurm/cgroup.conf
COPY modules.txt /etc/mock-slurm/modules.txt
COPY module /usr/local/bin/module
COPY codex-benchmark /usr/local/bin/codex-benchmark

RUN chown -R slurm:slurm /etc/slurm \
    && chmod 0600 /etc/slurm/slurmdbd.conf \
    && chmod 0755 /usr/local/bin/codex-benchmark /usr/local/bin/module

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

ENV DATA=/data

EXPOSE 22 6817 6818 6819

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["slurmdbd"]
