import logging
import os
import subprocess
from agent.identity.models import AgentIdentity

logger = logging.getLogger(__name__)

_PRIVATE_KEY_FILENAME = "agent_id_ed25519"
_PUBLIC_KEY_FILENAME = "agent_id_ed25519.pub"


class AgentIdentityService:
    def __init__(self, key_dir: str):
        self._key_dir = key_dir
        self._identity: AgentIdentity | None = None

    def ensure_agent_identity(self) -> AgentIdentity:
        """Load existing keypair if present; generate and persist a new one if not.

        Keypair consistency logic:
        - Both files present and consistent: return as-is.
        - Private key present, public key missing: regenerate public key from private key
          using `ssh-keygen -y -f <private_key_path>`.
        - Public key present, private key missing: raise RuntimeError.
        - Both files present but fingerprints do not match: raise RuntimeError.
        - Neither file present: generate fresh keypair.

        Private key permissions set to 0o600.
        """
        private_key_path = os.path.join(self._key_dir, _PRIVATE_KEY_FILENAME)
        public_key_path = os.path.join(self._key_dir, _PUBLIC_KEY_FILENAME)

        private_exists = os.path.exists(private_key_path)
        public_exists = os.path.exists(public_key_path)

        if not private_exists and not public_exists:
            # Generate fresh keypair
            logger.info("No agent keypair found. Generating new ed25519 keypair in %s", self._key_dir)
            os.makedirs(self._key_dir, exist_ok=True)
            try:
                subprocess.run(
                    ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", private_key_path],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"Failed to generate agent keypair: {e.stderr.strip()}"
                ) from e
            logger.info("Agent keypair generated successfully.")

        elif not private_exists and public_exists:
            raise RuntimeError(
                f"Agent public key exists at '{public_key_path}' but private key is missing at "
                f"'{private_key_path}'. Cannot recover — operator intervention required."
            )

        elif private_exists and not public_exists:
            # Regenerate public key from private key
            logger.info(
                "Public key missing. Regenerating from private key at %s", private_key_path
            )
            try:
                result = subprocess.run(
                    ["ssh-keygen", "-y", "-f", private_key_path],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"Failed to regenerate public key from private key '{private_key_path}': "
                    f"{e.stderr.strip()}"
                ) from e
            with open(public_key_path, "w") as f:
                f.write(result.stdout)
            logger.info("Public key regenerated at %s", public_key_path)

        # At this point both files must exist. Set permissions and parse.
        os.chmod(private_key_path, 0o600)

        # Parse public key content
        with open(public_key_path, "r") as f:
            public_key = f.read().strip()

        # Get fingerprint
        fingerprint = self._get_fingerprint(public_key_path)

        # If both files existed from the start, verify consistency
        if private_exists and public_exists:
            # Re-derive fingerprint from private key's public component to check consistency
            try:
                regen_result = subprocess.run(
                    ["ssh-keygen", "-y", "-f", private_key_path],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"Failed to read private key '{private_key_path}' for consistency check: "
                    f"{e.stderr.strip()}"
                ) from e
            derived_public_key = regen_result.stdout.strip()
            # Write derived key to a temp path to get its fingerprint
            import tempfile
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".pub", delete=False
            ) as tmp:
                tmp.write(derived_public_key + "\n")
                tmp_pub_path = tmp.name
            try:
                derived_fingerprint = self._get_fingerprint(tmp_pub_path)
            finally:
                os.unlink(tmp_pub_path)

            if fingerprint != derived_fingerprint:
                raise RuntimeError(
                    f"Agent keypair fingerprint mismatch: public key at '{public_key_path}' "
                    f"({fingerprint}) does not match private key at '{private_key_path}' "
                    f"({derived_fingerprint}). Operator intervention required."
                )

        self._identity = AgentIdentity(
            key_type="ed25519",
            public_key=public_key,
            fingerprint=fingerprint,
            private_key_path=private_key_path,
            public_key_path=public_key_path,
        )
        logger.info("Agent identity loaded. Fingerprint: %s", fingerprint)
        return self._identity

    def get_identity(self) -> AgentIdentity:
        """Return the current AgentIdentity.
        Raises RuntimeError if ensure_agent_identity() has not been called."""
        if self._identity is None:
            raise RuntimeError(
                "Agent identity has not been initialized. "
                "Call ensure_agent_identity() before get_identity()."
            )
        return self._identity

    def _get_fingerprint(self, public_key_path: str) -> str:
        """Extract SHA256 fingerprint from a public key file."""
        try:
            result = subprocess.run(
                ["ssh-keygen", "-l", "-E", "sha256", "-f", public_key_path],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to get fingerprint for '{public_key_path}': {e.stderr.strip()}"
            ) from e
        parts = result.stdout.split()
        try:
            fingerprint = next(p for p in parts if p.startswith("SHA256:"))
        except StopIteration:
            raise RuntimeError(
                f"Could not parse SHA256 fingerprint from ssh-keygen output: {result.stdout!r}"
            )
        return fingerprint
