"""Security utilities for API key generation, hashing, and verification."""

import secrets
import hashlib


def generate_api_key() -> str:
    """
    Generate a new API key with the format: agmkt_sk_{hex}.

    Returns:
        str: API key in format agmkt_sk_<64 hex characters>
    """
    random_hex = secrets.token_hex(32)  # 32 bytes = 64 hex characters
    return f"agmkt_sk_{random_hex}"


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key using SHA-256.

    Args:
        api_key: The plaintext API key

    Returns:
        str: SHA-256 hash of the API key as hex string
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(provided_key: str, stored_hash: str) -> bool:
    """
    Verify that a provided API key matches the stored hash.

    Args:
        provided_key: The API key provided by the user
        stored_hash: The stored SHA-256 hash

    Returns:
        bool: True if the key matches, False otherwise
    """
    return hash_api_key(provided_key) == stored_hash
