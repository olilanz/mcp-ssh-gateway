FROM ubuntu:24.04

# Install required packages
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    openssh-server \
    python3-pip \
    python3-venv \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create working directory and virtual environment
WORKDIR /app
RUN python3 -m venv /opt/venv

# Activate venv and install mcpo inside
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir mcpo

# Copy application code
COPY ./agent.py /app
COPY ./agent /app/agent
COPY ./scripts /app/scripts
COPY entrypoint.sh /entrypoint.sh

# Ensure entrypoint is executable
RUN chmod +x /entrypoint.sh

# Expose SSH port
EXPOSE 2222

# Default entrypoint
ENTRYPOINT ["/entrypoint.sh"]
