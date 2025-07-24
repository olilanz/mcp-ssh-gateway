import logging
import platform
import shutil
import os

def discover_shell():
    preferred = os.environ.get("SHELL")
    if preferred and shutil.which(preferred):
        return preferred

    # Fallback
    for shell in ["/bin/bash", "/bin/sh", "/usr/bin/zsh"]:
        if shutil.which(shell):
            return shell
    return "unknown"

def discover_os():
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "shell": discover_shell()
    }

def generate_discovery_script():
    return """#!/bin/sh
echo OS: $(uname -a)
echo Uptime: $(uptime)
echo Disks:
df -h
"""
