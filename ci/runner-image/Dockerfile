# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

# The CI runner image (stage 92): AlmaLinux 10 with every tool a
# cs-image-system configuration's CI calls, at pinned versions, placed where
# the starters' cfg/executables.yml pins them. docs/CI_RUNNER.md is the
# requirements this image implements; the versions here are the one list.
# Built and published by .github/workflows/runner-image.yml as
# ghcr.io/infrastructurebuilder/csis-ci:alma10-<YYYYMMDD>; a starter pins
# one such tag and `init-config --force` moves it with the other
# release-owned lines. The docker CLIENT alone is here: a job mounts the
# host's socket, and `mod_tests` drives the host daemon through it.
#
# The base is pinned by digest (almalinux:10.2, amd64, read 2026-10-16).
ARG BASE_DIGEST=sha256:838c2fafefb1a8a0d7f8cdbc3b0551c2a2b1eb0cd87aad6d62aecadb18311f1b
FROM --platform=linux/amd64 docker.io/library/almalinux:10@${BASE_DIGEST}

# ---- the pins: one line per tool, read by the probe and by docs/CI_RUNNER.md's test
ARG UV_VERSION=0.12.18
ARG JUST_VERSION=1.56.0
ARG TOFU_VERSION=1.12.6
ARG PACKER_VERSION=1.14.3
ARG AWSCLI_VERSION=2.37.1
ARG SSM_PLUGIN_VERSION=1.2.835.0
ARG GCLOUD_VERSION=589.0.0
# Google's rpm signing key is refused by EL10's rpm policy ("No binding signature at
# time ...", read 2026-10-16), so the Cloud CLI comes from Google's versioned archive,
# pinned by its checksum (computed on 2026-10-16; a new version gets a new checksum).
ARG GCLOUD_SHA256=f865da648f6fdae2015abb5b32eaa0eb10520e88f0ca735cfb33795868c8d26f
ARG SFT_VERSION=1.115.0
ARG DOCKER_CLI_VERSION=29.9.1
ARG ANSIBLE_CORE_VERSION=2.21.4
ARG YQ_VERSION=4.53.6
# AlmaLinux 10's own jq answers `jq --version` with "jq-" and no number (read
# 2026-10-16), which the system's version floor would refuse; upstream's binary does
ARG JQ_VERSION=1.8.2
ARG AGE_VERSION=1.3.2
ARG PYTHON_VERSION=3.13

LABEL org.opencontainers.image.title="csis-ci" \
      org.opencontainers.image.description="AlmaLinux 10 CI runner for cs-image-system configuration repositories (stage 92)" \
      org.opencontainers.image.source="https://github.com/infrastructurebuilder/cs-image-system-3" \
      org.opencontainers.image.licenses="Apache-2.0"

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

# ---- the distribution's own: git, jq, bash 5, sudo (the workflows' `sudo ln -sf` lines
# keep working as root), ssh (sft ssh and the SSM ProxyCommand), unzip/tar for the archives
RUN dnf -y -q install git sudo openssh-clients unzip tar gzip which findutils procps-ng ca-certificates \
        python3 \
    && dnf -y -q clean all \
    && ln -sf /usr/bin/bash /usr/local/bin/bash \
    # a job's checkout is owned by the runner's user while the container runs as root, and git
    # refuses such a directory ("fatal: not in a git directory" from `git config` on the first
    # run inside the image, 2026-10-16); every job commits, scans or configures in that checkout
    && git config --system --add safe.directory '*'

# ---- the vendors' EL10 repositories, each pinned to one package version
RUN cat > /etc/yum.repos.d/docker-ce.repo <<'REPO'
[docker-ce-stable]
name=Docker CE Stable
baseurl=https://download.docker.com/linux/rhel/10/$basearch/stable
enabled=1
gpgcheck=1
gpgkey=https://download.docker.com/linux/rhel/gpg
REPO
RUN cat > /etc/yum.repos.d/oktapam.repo <<'REPO'
[oktapam-stable]
name=Okta Privileged Access, stable
baseurl=https://dist.scaleft.com/repos/rpm/stable/rhel/10/$basearch
enabled=1
gpgcheck=1
gpgkey=https://dist.scaleft.com/GPG-KEY-OktaPAM-2023
REPO
RUN dnf -y -q install "docker-ce-cli-1:${DOCKER_CLI_VERSION}-1.el10" \
                      "scaleft-client-tools-${SFT_VERSION}-1.el10" \
    && dnf -y -q clean all \
    && ln -sf /usr/bin/docker /usr/local/bin/docker

# ---- the Google Cloud CLI from its versioned archive (see GCLOUD_SHA256 above)
RUN curl -fsSL "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-${GCLOUD_VERSION}-linux-x86_64.tar.gz" \
        -o /tmp/google-cloud-cli.tar.gz \
    && echo "${GCLOUD_SHA256}  /tmp/google-cloud-cli.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/google-cloud-cli.tar.gz -C /usr/local && rm -f /tmp/google-cloud-cli.tar.gz \
    && /usr/local/google-cloud-sdk/install.sh --quiet --usage-reporting=false --path-update=false \
        --command-completion=false --bash-completion=false --rc-path=/dev/null >/dev/null \
    && ln -sf /usr/local/google-cloud-sdk/bin/gcloud /usr/local/bin/gcloud \
    && ln -sf /usr/local/google-cloud-sdk/bin/gsutil /usr/local/bin/gsutil \
    && rm -rf /usr/local/google-cloud-sdk/.install/.backup

# ---- the pinned release archives: uv, just, OpenTofu, Packer, yq, age
RUN curl -fsSL "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" \
        | tar -xz -C /usr/local/bin --strip-components=1 uv-x86_64-unknown-linux-gnu/uv uv-x86_64-unknown-linux-gnu/uvx \
    && curl -fsSL "https://github.com/casey/just/releases/download/${JUST_VERSION}/just-${JUST_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
        | tar -xz -C /usr/local/bin just \
    && curl -fsSL "https://github.com/opentofu/opentofu/releases/download/v${TOFU_VERSION}/tofu_${TOFU_VERSION}_linux_amd64.tar.gz" \
        | tar -xz -C /usr/local/bin tofu \
    && curl -fsSL "https://releases.hashicorp.com/packer/${PACKER_VERSION}/packer_${PACKER_VERSION}_linux_amd64.zip" -o /tmp/packer.zip \
    && unzip -q -o /tmp/packer.zip packer -d /usr/local/bin && rm -f /tmp/packer.zip \
    && curl -fsSL "https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/yq_linux_amd64" -o /usr/local/bin/yq \
    && curl -fsSL "https://github.com/jqlang/jq/releases/download/jq-${JQ_VERSION}/jq-linux-amd64" -o /usr/local/bin/jq \
    && curl -fsSL "https://github.com/FiloSottile/age/releases/download/v${AGE_VERSION}/age-v${AGE_VERSION}-linux-amd64.tar.gz" \
        | tar -xz -C /usr/local/bin --strip-components=1 age/age age/age-keygen \
    && chmod 0755 /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/just /usr/local/bin/tofu /usr/local/bin/packer \
                  /usr/local/bin/yq /usr/local/bin/jq /usr/local/bin/age /usr/local/bin/age-keygen

# ---- the AWS CLI v2 and the Session Manager plugin, from AWS's own archives
RUN curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64-${AWSCLI_VERSION}.zip" -o /tmp/awscliv2.zip \
    && unzip -q /tmp/awscliv2.zip -d /tmp && /tmp/aws/install --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli \
    && rm -rf /tmp/aws /tmp/awscliv2.zip \
    && curl -fsSL "https://s3.amazonaws.com/session-manager-downloads/plugin/${SSM_PLUGIN_VERSION}/linux_64bit/session-manager-plugin.rpm" \
        -o /tmp/session-manager-plugin.rpm \
    && dnf -y -q install /tmp/session-manager-plugin.rpm && rm -f /tmp/session-manager-plugin.rpm && dnf -y -q clean all

# ---- the Python the released system runs on, and ansible-core as a uv tool
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_TOOL_DIR=/opt/uv/tools \
    UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_LINK_MODE=copy
RUN uv python install "${PYTHON_VERSION}" \
    && uv tool install "ansible-core==${ANSIBLE_CORE_VERSION}" --python "${PYTHON_VERSION}" \
    && test -x /usr/local/bin/ansible-playbook

# ---- the one list, for the probe and the requirements document's test
RUN mkdir -p /etc/csis-ci && cat > /etc/csis-ci/tools.txt <<EOT
uv ${UV_VERSION}
just ${JUST_VERSION}
tofu ${TOFU_VERSION}
packer ${PACKER_VERSION}
aws-cli ${AWSCLI_VERSION}
session-manager-plugin ${SSM_PLUGIN_VERSION}
gcloud ${GCLOUD_VERSION}
sft ${SFT_VERSION}
docker-cli ${DOCKER_CLI_VERSION}
ansible-core ${ANSIBLE_CORE_VERSION}
yq ${YQ_VERSION}
jq ${JQ_VERSION}
age ${AGE_VERSION}
python ${PYTHON_VERSION}
EOT

# The probe: every tool answers --version from where cfg/executables.yml pins it
COPY probe.sh /usr/local/bin/csis-ci-probe
RUN chmod 0755 /usr/local/bin/csis-ci-probe && csis-ci-probe

CMD ["/bin/bash"]
