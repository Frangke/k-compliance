"""AES-256-GCM helpers for encrypting cloud credentials at rest.

**Contract**: `settings.ENCRYPTION_KEY` must be a 256-bit random value
(generate with `openssl rand -hex 32`). The SHA-256 pass below is a
deterministic reshape to exactly 32 bytes for AES-256, not a KDF —
no strengthening against weak inputs is performed on purpose.

PBKDF2/Argon2 was considered and rejected (see
`docs/adr/0004-retire-encryption-key-kdf.md`): if the caller honors the
256-bit-random contract, no KDF adds security; if the caller violates
it, a KDF can't save them from an attacker who already has `.env`.
"""

import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _master_key() -> bytes:
    return hashlib.sha256(settings.ENCRYPTION_KEY.encode("utf-8")).digest()


def encrypt_bytes(plaintext: bytes) -> bytes:
    """Encrypt with AES-256-GCM. Output = 12-byte nonce || ciphertext_with_tag."""
    nonce = os.urandom(12)
    cipher = AESGCM(_master_key())
    ct = cipher.encrypt(nonce, plaintext, None)
    return nonce + ct


def decrypt_bytes(blob: bytes) -> bytes:
    """Decrypt AES-256-GCM blob (first 12 bytes = nonce)."""
    nonce, ct = blob[:12], blob[12:]
    cipher = AESGCM(_master_key())
    return cipher.decrypt(nonce, ct, None)


def encrypt_json(payload: dict) -> bytes:
    return encrypt_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def decrypt_json(blob: bytes) -> dict:
    return json.loads(decrypt_bytes(blob).decode("utf-8"))
