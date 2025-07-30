import requests
import time

def wait_for_http_ready(port=8000, path="/v1/models", timeout=30):
    """
    Wait for an HTTP endpoint to become ready.

    Args:
        port (int): The port to check.
        path (str): The HTTP path to check.
        timeout (int): The maximum time to wait in seconds.

    Returns:
        requests.Response: The HTTP response if the endpoint is ready.

    Raises:
        TimeoutError: If the endpoint does not become ready within the timeout.
    """
    url = f"http://localhost:{port}{path}"
    for _ in range(timeout):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response
        except requests.ConnectionError:
            time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {url}")