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
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
        f.write(f"Port {free_port}\n")  # Dynamically bind to a free port
        f.write("HostKey {}/rsa_host_key\n".format(temp_dir.name))
        f.write("HostKeyAlgorithms +ssh-rsa\n")
        f.write("PubkeyAcceptedAlgorithms +ssh-rsa\n")
        f.write("DisableDSA yes\n")
        f.write("HostKeyAlgorithms +ssh-rsa\n")
        f.write("PubkeyAcceptedAlgorithms +ssh-rsa\n")
        f.write("PidFile {}/sshd.pid\n".format(temp_dir.name))
        f.write("ListenAddress 127.0.0.1\n")
        f.write("PermitRootLogin no\n")
        f.write("PasswordAuthentication no\n")
        f.write("ChallengeResponseAuthentication no\n")
        f.write("UsePAM no\n")

    # Ensure /run/sshd directory exists
    subprocess.run(["ssh-keygen", "-t", "rsa", "-f", "{}/rsa_host_key".format(temp_dir.name), "-N", ""], check=True)
    subprocess.run(["mkdir", "-p", "/run/sshd"], check=True)

    # Start sshd as a subprocess
    sshd_process = subprocess.Popen(
        ["/usr/sbin/sshd", "-D", "-f", sshd_config, "-E", "{}/sshd.log".format(temp_dir.name)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    # Wait for sshd to start
    time.sleep(1)
    with open("{}/sshd.log".format(temp_dir.name), "r") as log_file:
        log_content = log_file.read()
        print(f"SSHD Log Content: {log_content}")
    with open("{}/sshd.pid".format(temp_dir.name)) as pid_file:
        pid = int(pid_file.read().strip())
    port = free_port  # Use the dynamically allocated port directly

    class SSHD:
        def __init__(self, host, port, user, agent_id_file):
            self.host = host
            self.port = port
            self.user = user
            self.agent_id_file = agent_id_file

    yield SSHD(
        host="127.0.0.1",
        port=port,
        user="test-user",
        agent_id_file="/tmp/test-agent-id-file"
    )

    # Cleanup
    sshd_process.terminate()
    temp_dir.cleanup()