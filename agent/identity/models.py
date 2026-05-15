from dataclasses import dataclass


@dataclass(frozen=True)
class AgentIdentity:
    key_type: str           # always "ed25519"
    public_key: str         # full OpenSSH public key string, e.g. "ssh-ed25519 AAAA..."
    fingerprint: str        # SHA256 fingerprint, e.g. "SHA256:abc123..."
    private_key_path: str   # absolute path to private key file — path only, not key material
    public_key_path: str    # absolute path to public key file — path only, not key material
