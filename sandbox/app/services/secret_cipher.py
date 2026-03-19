import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


_TOKEN_PREFIX = "enc:v1:"


class SecretCipher:
    """Encrypt/decrypt short sensitive secrets for local persistence."""

    def __init__(self, secret_seed: str):
        if not secret_seed or not secret_seed.strip():
            raise ValueError("secret_seed is required")
        digest = hashlib.sha256(secret_seed.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None:
            raise ValueError("plaintext is required")
        encrypted = self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return f"{_TOKEN_PREFIX}{encrypted}"

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext or not ciphertext.startswith(_TOKEN_PREFIX):
            raise ValueError("ciphertext format is invalid")
        payload = ciphertext[len(_TOKEN_PREFIX) :]
        try:
            return self._fernet.decrypt(payload.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("ciphertext cannot be decrypted") from exc

