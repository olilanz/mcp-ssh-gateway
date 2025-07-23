#!/bin/sh

# Script: os_info.sh
# Purpose: Return basic OS info in JSON format for MCP agent

echo '{'
echo "  \"os_name\": \"$(uname -s)\","
echo "  \"os_version\": \"$(uname -r)\","
echo "  \"architecture\": \"$(uname -m)\""
echo '}'
