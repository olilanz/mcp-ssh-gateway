import os
import pytest
from agent.identity.service import AgentIdentityService


def test_ensure_creates_keypair_if_missing(tmp_path):
    """When no keys exist, ensure_agent_identity() creates both key files."""
    service = AgentIdentityService(key_dir=str(tmp_path))
    identity = service.ensure_agent_identity()

    assert os.path.exists(identity.private_key_path)
    assert os.path.exists(identity.public_key_path)


def test_ensure_returns_ed25519_key_type(tmp_path):
    """identity.key_type == 'ed25519'"""
    service = AgentIdentityService(key_dir=str(tmp_path))
    identity = service.ensure_agent_identity()

    assert identity.key_type == "ed25519"


def test_ensure_public_key_starts_with_ssh_ed25519(tmp_path):
    """identity.public_key starts with 'ssh-ed25519 '"""
    service = AgentIdentityService(key_dir=str(tmp_path))
    identity = service.ensure_agent_identity()

    assert identity.public_key.startswith("ssh-ed25519 ")


def test_ensure_fingerprint_starts_with_sha256(tmp_path):
    """identity.fingerprint starts with 'SHA256:'"""
    service = AgentIdentityService(key_dir=str(tmp_path))
    identity = service.ensure_agent_identity()

    assert identity.fingerprint.startswith("SHA256:")


def test_ensure_reuses_existing_keypair(tmp_path):
    """Calling ensure_agent_identity() twice returns the same public_key."""
    service = AgentIdentityService(key_dir=str(tmp_path))
    identity1 = service.ensure_agent_identity()

    # Create a second service instance pointing to the same directory
    service2 = AgentIdentityService(key_dir=str(tmp_path))
    identity2 = service2.ensure_agent_identity()

    assert identity1.public_key == identity2.public_key


def test_private_key_permissions_are_0600(tmp_path):
    """Private key file must have permissions 0o600."""
    service = AgentIdentityService(key_dir=str(tmp_path))
    identity = service.ensure_agent_identity()

    mode = os.stat(identity.private_key_path).st_mode & 0o777
    assert mode == 0o600


def test_private_key_string_not_in_identity_fields(tmp_path):
    """AgentIdentity has no string field containing raw private key material
    (no field value starts with '-----BEGIN')."""
    service = AgentIdentityService(key_dir=str(tmp_path))
    identity = service.ensure_agent_identity()

    for field_name, field_value in identity.__dataclass_fields__.items():
        value = getattr(identity, field_name)
        if isinstance(value, str):
            assert not value.startswith("-----BEGIN"), (
                f"Field '{field_name}' appears to contain private key material"
            )


def test_get_identity_raises_if_not_ensured(tmp_path):
    """get_identity() before ensure_agent_identity() raises RuntimeError."""
    service = AgentIdentityService(key_dir=str(tmp_path))

    with pytest.raises(RuntimeError):
        service.get_identity()


def test_missing_public_key_is_regenerated(tmp_path):
    """Delete public key after generation; call ensure_agent_identity() again;
    public key file is recreated with same fingerprint."""
    service = AgentIdentityService(key_dir=str(tmp_path))
    identity1 = service.ensure_agent_identity()
    original_fingerprint = identity1.fingerprint

    # Delete the public key
    os.unlink(identity1.public_key_path)
    assert not os.path.exists(identity1.public_key_path)

    # Re-run ensure — should regenerate the public key
    service2 = AgentIdentityService(key_dir=str(tmp_path))
    identity2 = service2.ensure_agent_identity()

    assert os.path.exists(identity2.public_key_path)
    assert identity2.fingerprint == original_fingerprint


def test_missing_private_key_raises(tmp_path):
    """If only the public key file exists, ensure_agent_identity() raises RuntimeError."""
    # Create only a public key file (simulate partial state)
    public_key_path = tmp_path / "agent_id_ed25519.pub"
    public_key_path.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeKeyForTesting agent@gateway\n")

    service = AgentIdentityService(key_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match="private key is missing"):
        service.ensure_agent_identity()


def test_inconsistent_keypair_raises(tmp_path):
    """Generate two keypairs; replace public key with the second keypair's public key;
    ensure_agent_identity() raises RuntimeError due to fingerprint mismatch."""
    import subprocess

    # Generate first keypair in tmp_path
    service1 = AgentIdentityService(key_dir=str(tmp_path))
    identity1 = service1.ensure_agent_identity()

    # Generate a second keypair in a different directory
    second_dir = tmp_path / "second"
    second_dir.mkdir()
    service2 = AgentIdentityService(key_dir=str(second_dir))
    identity2 = service2.ensure_agent_identity()

    # Replace the first keypair's public key with the second keypair's public key
    with open(identity2.public_key_path, "r") as f:
        second_public_key = f.read()
    with open(identity1.public_key_path, "w") as f:
        f.write(second_public_key)

    # Now the keypair is inconsistent — private key from first, public key from second
    service3 = AgentIdentityService(key_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match="fingerprint mismatch"):
        service3.ensure_agent_identity()


def test_ensure_does_not_log_private_key_content(tmp_path, caplog):
    """Private key material must never appear in logs during identity generation."""
    import logging
    service = AgentIdentityService(str(tmp_path))
    with caplog.at_level(logging.DEBUG):
        identity = service.ensure_agent_identity()
    # Read the actual private key file content
    with open(identity.private_key_path) as f:
        private_key_content = f.read()
    # Verify no part of the private key appears in any log record
    for record in caplog.records:
        assert "-----BEGIN" not in record.message, \
            "Private key PEM header must not appear in logs"
        assert private_key_content[:20] not in record.message, \
            "Private key content must not appear in logs"


def test_non_ed25519_public_key_raises(tmp_path):
    """If an existing public key is not ed25519 type, ensure_agent_identity raises RuntimeError."""
    import subprocess
    service = AgentIdentityService(str(tmp_path))
    private_key = tmp_path / "agent_id_ed25519"
    public_key = tmp_path / "agent_id_ed25519.pub"
    # Generate an RSA keypair instead
    subprocess.run(
        ["ssh-keygen", "-t", "rsa", "-b", "2048", "-N", "", "-f", str(private_key)],
        check=True, capture_output=True
    )
    # Verify public key starts with ssh-rsa (not ed25519)
    with pytest.raises(RuntimeError, match="not an ed25519 key"):
        service.ensure_agent_identity()
