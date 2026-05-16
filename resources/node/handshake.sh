#!/bin/sh
# Node handshake — minimal facts for NodeInfoCache.
# POSIX sh compatible. No jq. No non-standard tools.
# Output: key=value pairs, one per line using printf.
# Values may contain spaces and = signs; parser splits on first = only.

printf 'hostname=%s\n'       "$(hostname 2>/dev/null || printf '')"
printf 'kernel_name=%s\n'    "$(uname -s 2>/dev/null || printf '')"
printf 'kernel_release=%s\n' "$(uname -r 2>/dev/null || printf '')"
printf 'architecture=%s\n'   "$(uname -m 2>/dev/null || printf '')"
printf 'current_user=%s\n'   "$(whoami 2>/dev/null || printf '')"
printf 'shell=%s\n'          "${SHELL:-}"

os_pretty_name=""
if [ -r /etc/os-release ]; then
    . /etc/os-release
    os_pretty_name="${PRETTY_NAME:-}"
fi
if [ -z "$os_pretty_name" ]; then
    os_pretty_name="$(uname -s 2>/dev/null || printf '')"
fi
printf 'os_pretty_name=%s\n' "$os_pretty_name"

printf 'collected_at=%s\n'   "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || printf '')"
