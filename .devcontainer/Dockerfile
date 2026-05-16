FROM ubuntu:24.04

# Install runtime environment — same system packages as production,
# plus dev tools (git). No app code is copied here; the workspace is
# bind-mounted at /workspaces/mcp-ssh-gateway by devcontainer.json.
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    openssh-server \
    openssh-client \
    curl \
    iproute2 \
    libffi-dev libssl-dev \
    python3-pip \
    sudo \
    git \
    && apt-get remove -y python3-jwt \
    && rm -rf /var/lib/apt/lists/*

# Create vscode user for devcontainer sessions (idempotent).
# Handles Ubuntu 24.04 base images where uid/gid 1000 already belongs to "ubuntu".
RUN if ! id -u vscode >/dev/null 2>&1; then \
      if id -u ubuntu >/dev/null 2>&1; then \
        usermod -l vscode -d /home/vscode -m ubuntu; \
        if getent group ubuntu >/dev/null 2>&1 && ! getent group vscode >/dev/null 2>&1; then \
          groupmod -n vscode ubuntu; \
        fi; \
      else \
        if ! getent group vscode >/dev/null; then \
          if getent group 1000 >/dev/null; then groupadd vscode; else groupadd --gid 1000 vscode; fi; \
        fi; \
        useradd -m -s /bin/bash -g vscode vscode; \
      fi; \
    fi \
    && usermod -aG sudo vscode \
    && printf 'vscode ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/90-vscode \
    && chmod 0440 /etc/sudoers.d/90-vscode

# Ensure user-local pip scripts are on PATH for the vscode user
ENV PATH="/home/vscode/.local/bin:${PATH}"

# Pre-create Roo extension storage path so the named volume inherits vscode
# ownership when Docker seeds it from the image on first creation.
RUN install -d -m 0755 -o vscode -g vscode \
      /home/vscode/.vscode-server \
      /home/vscode/.vscode-server/data \
      /home/vscode/.vscode-server/data/User \
      /home/vscode/.vscode-server/data/User/globalStorage \
      /home/vscode/.vscode-server/data/User/globalStorage/rooveterinaryinc.roo-cline

# ── Test isolation user ──────────────────────────────────────────────────────
# The `sshbootstrap` user exists solely to support functional tests for the
# add_node password-bootstrap flow (tests/functional/test_add_node_functional.py).
# Its password is hard-coded and intentionally weak because it is only
# reachable from 127.0.0.1 inside an ephemeral test sshd instance.
# This user MUST NOT be used for any production purpose.
RUN useradd -m -s /bin/sh sshbootstrap \
    && echo 'sshbootstrap:sshbootstrap' | chpasswd

# No ENTRYPOINT — devcontainer lifecycle is managed by VS Code.
