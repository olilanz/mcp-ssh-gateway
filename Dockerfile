FROM ubuntu:22.04

# Install required packages
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    openssh-server \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /app

# Copy application code
COPY ./agent /app/agent
COPY ./scripts /app/scripts
COPY entrypoint.sh /entrypoint.sh

# Ensure entrypoint is executable
RUN chmod +x /entrypoint.sh

# Expose SSH port (only relevant in inbound mode)
EXPOSE 2222

# Default entrypoint
ENTRYPOINT ["/entrypoint.sh"]
