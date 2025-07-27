import pytest
import subprocess
import tempfile
import os
import time


@pytest.fixture(scope="module")
def sshd_fixture():
    # Create a temporary directory for sshd configuration
    temp_dir = tempfile.TemporaryDirectory()
    sshd_config = os.path.join(temp_dir.name, "sshd_config")

    # Write minimal sshd configuration
    with open(sshd_config, "w") as f:
        f.write("Port 0\n")  # Bind to a random port
        f.write("ListenAddress 127.0.0.1\n")
        f.write("PermitRootLogin no\n")
        f.write("PasswordAuthentication no\n")
        f.write("ChallengeResponseAuthentication no\n")
        f.write("UsePAM no\n")

    # Start sshd as a subprocess
    sshd_process = subprocess.Popen(
        ["sshd", "-D", "-f", sshd_config],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    # Wait for sshd to start
    time.sleep(1)

    yield {
        "host": "127.0.0.1",
        "port": 22,  # Replace with a fixed port for simplicity
    }

    # Cleanup
    sshd_process.terminate()
    temp_dir.cleanup()