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
        f.write("Port 8022\n")  # Bind to a high port for testing
        f.write("PidFile {}/sshd.pid\n".format(temp_dir.name))
        f.write("ListenAddress 127.0.0.1\n")
        f.write("PermitRootLogin no\n")
        f.write("PasswordAuthentication no\n")
        f.write("ChallengeResponseAuthentication no\n")
        f.write("UsePAM no\n")

    # Start sshd as a subprocess
    sshd_process = subprocess.Popen(
        subprocess.run(["mkdir", "-p", "/run/sshd"], check=True)
        sshd_process = subprocess.Popen(
            ["/usr/sbin/sshd", "-D", "-f", sshd_config, "-E", "{}/sshd.log".format(temp_dir.name)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        sshd_process = subprocess.Popen(
            ["/usr/sbin/sshd", "-D", "-f", sshd_config, "-E", "{}/sshd.log".format(temp_dir.name)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        sshd_process = subprocess.Popen(
            ["/usr/sbin/sshd", "-D", "-f", sshd_config, "-E", "{}/sshd.log".format(temp_dir.name)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    # Wait for sshd to start
    time.sleep(1)
    with open("{}/sshd.log".format(temp_dir.name), "r") as log_file:
        log_content = log_file.read()
        print(f"SSHD Log Content: {log_content}")
    stderr_output = sshd_process.stderr.read()
    if stderr_output:
        if "permission denied" in stderr_output.lower():
            raise PermissionError(f"SSHD failed to start due to permission issues: {stderr_output}")
        raise RuntimeError(f"SSHD failed to start: {stderr_output}")
    stderr_output = sshd_process.stderr.read()
    print(f"SSHD Error Output: {stderr_output}")
    with open("{}/sshd.pid".format(temp_dir.name)) as pid_file:
        pid = int(pid_file.read().strip())
    port = subprocess.check_output(["lsof", "-Pan", "-p", str(pid), "-i", "-n"], text=True)
    port = int([line.split(":")[-1].split("->")[0] for line in port.splitlines() if "LISTEN" in line][0])

    yield {
        "host": "127.0.0.1",
        "port": port,
    }

    # Cleanup
    sshd_process.terminate()
    temp_dir.cleanup()