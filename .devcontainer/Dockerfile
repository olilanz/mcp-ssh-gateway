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
    fi

# Ensure user-local pip scripts are on PATH for the vscode user
ENV PATH="/home/vscode/.local/bin:${PATH}"

# Pre-create .roo so the named volume for Roo history inherits vscode ownership
# when Docker seeds it from the image on first creation.
RUN install -d -m 0755 -o vscode -g vscode /home/vscode/.roo

# No ENTRYPOINT — devcontainer lifecycle is managed by VS Code.
