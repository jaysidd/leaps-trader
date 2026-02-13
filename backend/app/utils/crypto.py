"""
Credential encryption utilities using Fernet (AES-128-CBC).

Provides encrypt/decrypt helpers for storing broker passwords at rest.
The encryption key is read from settings (CREDENTIAL_ENCRYPTION_KEY).
If no key is configured, one is auto-generated and appended to .env.
"""
import os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from loguru import logger


# Module-level cache for the Fernet instance
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """
    Get (or create) a Fernet instance using the configured encryption key.

    On first call, reads CREDENTIAL_ENCRYPTION_KEY from settings. If the key
    is empty, generates a new one and appends it to the .env file so it
    persists across server restarts.
    """
    global _fernet
    if _fernet is not None:
        return _fernet

    from app.config import get_settings
    settings = get_settings()
    key = settings.CREDENTIAL_ENCRYPTION_KEY

    if not key:
        # Auto-generate a new Fernet key
        key = Fernet.generate_key().decode()
        logger.warning(
            "🔐 No CREDENTIAL_ENCRYPTION_KEY configured. "
            "Auto-generated a new key. Appending to .env file."
        )
        _append_key_to_env(key)
        # Update the settings in-memory so subsequent calls use the same key
        object.__setattr__(settings, "CREDENTIAL_ENCRYPTION_KEY", key)

    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def _append_key_to_env(key: str) -> None:
    """Append the encryption key to the .env file."""
    env_path = Path(".env")
    try:
        # Read existing content to check if key already there
        existing = env_path.read_text() if env_path.exists() else ""
        if "CREDENTIAL_ENCRYPTION_KEY" not in existing:
            with open(env_path, "a") as f:
                f.write(f"\n# Auto-generated credential encryption key (do NOT share)\n")
                f.write(f"CREDENTIAL_ENCRYPTION_KEY={key}\n")
            logger.info(f"🔑 Encryption key saved to {env_path.absolute()}")
        else:
            logger.info("CREDENTIAL_ENCRYPTION_KEY already exists in .env — skipping write")
    except Exception as e:
        logger.error(f"Could not write encryption key to .env: {e}")
        logger.warning(
            f"Please manually add to .env:\n"
            f"CREDENTIAL_ENCRYPTION_KEY={key}"
        )


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a plaintext string using Fernet.

    Returns a URL-safe base64-encoded encrypted string.
    """
    if not plaintext:
        return ""
    fernet = _get_fernet()
    encrypted = fernet.encrypt(plaintext.encode())
    return encrypted.decode()


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypt a Fernet-encrypted string back to plaintext.

    Returns the original plaintext string.
    Raises ValueError if the ciphertext is invalid or the key has changed.
    """
    if not ciphertext:
        return ""
    fernet = _get_fernet()
    try:
        decrypted = fernet.decrypt(ciphertext.encode())
        return decrypted.decode()
    except InvalidToken:
        logger.error(
            "❌ Failed to decrypt credential — encryption key may have changed. "
            "User will need to re-connect their broker account."
        )
        raise ValueError("Cannot decrypt stored credential. Encryption key may have changed.")
