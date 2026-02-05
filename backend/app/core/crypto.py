"""Encryption utilities for sensitive data (e.g., BYOK API keys)."""

from cryptography.fernet import Fernet

from app.config import settings


def _get_fernet() -> Fernet:
    key = settings.LLM_CREDENTIALS_MASTER_KEY
    if not key:
        raise RuntimeError("LLM_CREDENTIALS_MASTER_KEY is not set")
    return Fernet(key.encode("utf-8"))


def encrypt_secret(plaintext: str) -> str:
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    fernet = _get_fernet()
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
