import subprocess
import json
import signal
import time

def test_app_stdio_get_status():
    """
    Test that app.py responds correctly to an MCP get_status request over stdin/stdout.
    """
    proc = subprocess.Popen(
        ["python3", "app.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    try:
        # Construct MCP get_status request
        msg = json.dumps({"method": "get_status", "params": {}})
        proc.stdin.write(msg + "\n")
        proc.stdin.flush()

        # Read and parse the response
        response_line = proc.stdout.readline()
        if not response_line:
            print("STDOUT OUTPUT:", proc.stdout.read())
            print("STDERR OUTPUT:", proc.stderr.read())
        response = json.loads(response_line)

        # Assert the response is successful and ready
        assert response["success"] is True
        assert response["data"]["ready"] is True

        # Add a short delay before sending SIGTERM
        time.sleep(1)
    finally:
        # Send SIGTERM to initiate shutdown
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print("Process did not terminate after SIGTERM. Forcing termination.")
            proc.kill()