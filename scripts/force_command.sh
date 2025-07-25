#!/bin/bash
set -e

echo "Executing force_command script..."

METADATA_DIR="/app/metadata"
mkdir -p "$METADATA_DIR"

TIMESTAMP=$(date +%s)
FILE="$METADATA_DIR/edge_${TIMESTAMP}.json"

# read metadata from stdin and write to file
echo "Reading metadata from stdin..."

read METADATA
echo "$METADATA" > "$FILE"

echo "Metadata written to $FILE"

# Send agent's pubkey as response
echo "Sending agent's public key..."
cat /keys/id_rsa.pub
echo "Public key sent successfully."

exit 0
