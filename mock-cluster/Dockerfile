FROM rockylinux:9

LABEL org.opencontainers.image.source="https://github.com/aboucaud/benchmarking-hpc-skills" \
      org.opencontainers.image.title="mock-slurm-cluster" \
      org.opencontainers.image.description="Two-node Slurm cluster for local testing"

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
        gnupg2 \
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
        openssh-server \
        perl \
        procps-ng \
        psmisc \
        sudo \
        systemd-devel \
        wget \
    && dnf clean all \
    && rm -rf /var/cache/dnf

RUN set -eux \
    && useradd --create-home --shell /bin/bash submitter \
    && echo "submitter:submitter" | chpasswd \
    && usermod --append --groups wheel submitter \
    && echo "%wheel ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers \
    && ssh-keygen -A \
    && mkdir -p /run/sshd \
    && { \
        echo "# Local test cluster only"; \
        echo "PasswordAuthentication yes"; \
        echo "UsePAM no"; \
        echo "PermitRootLogin no"; \
    } > /etc/ssh/sshd_config.d/50-mock-slurm.conf

COPY submitter.bashrc /home/submitter/.bashrc
RUN chown submitter:submitter /home/submitter/.bashrc \
    && chmod 0644 /home/submitter/.bashrc

ARG GOSU_VERSION=1.17
ARG TARGETARCH

RUN set -eux \
    && case "${TARGETARCH}" in \
        amd64|arm64) gosu_arch="${TARGETARCH}" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && wget -O /usr/local/bin/gosu \
        "https://github.com/tianon/gosu/releases/download/${GOSU_VERSION}/gosu-${gosu_arch}" \
    && wget -O /usr/local/bin/gosu.asc \
        "https://github.com/tianon/gosu/releases/download/${GOSU_VERSION}/gosu-${gosu_arch}.asc" \
    && export GNUPGHOME="$(mktemp -d)" \
    && gpg --batch --keyserver hkps://keys.openpgp.org \
        --recv-keys B42F6819007F00F88E364FD4036A9C25BF357DD4 \
    && gpg --batch --verify /usr/local/bin/gosu.asc /usr/local/bin/gosu \
    && rm -rf "${GNUPGHOME}" /usr/local/bin/gosu.asc \
    && chmod 0755 /usr/local/bin/gosu \
    && gosu nobody true

ARG SLURM_TAG=slurm-25-11-2-1

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
    && make -j"$(nproc)" \
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
        /data \
        /etc/slurm \
        /run/munge \
        /var/lib/slurm \
        /var/lib/slurmd \
        /var/log/slurm \
        /var/run/slurmctld \
        /var/run/slurmd \
        /var/run/slurmdbd \
        /var/spool/slurmctld \
        /var/spool/slurmd \
    && chown submitter:submitter /data \
    && chown -R munge:munge /run/munge \
    && chown -R slurm:slurm \
        /var/lib/slurm \
        /var/log/slurm \
        /var/run/slurmctld \
        /var/run/slurmdbd \
        /var/spool/slurmctld \
    && /sbin/create-munge-key

COPY slurm.conf /etc/slurm/slurm.conf
COPY slurmdbd.conf /etc/slurm/slurmdbd.conf
COPY cgroup.conf /etc/slurm/cgroup.conf

RUN chown -R slurm:slurm /etc/slurm \
    && chmod 0600 /etc/slurm/slurmdbd.conf

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

ENV DATA=/data

EXPOSE 22 6817 6818 6819

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["slurmdbd"]
