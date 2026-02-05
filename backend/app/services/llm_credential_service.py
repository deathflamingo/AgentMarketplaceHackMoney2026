"""Service for managing encrypted LLM provider credentials."""

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.crypto import encrypt_secret, decrypt_secret
from app.models.llm_credential import LLMProviderCredential, LLMProvider


async def upsert_credential(
    db: AsyncSession,
    *,
    agent_id: str,
    provider: LLMProvider,
    api_key: str
) -> LLMProviderCredential:
    result = await db.execute(
        select(LLMProviderCredential).where(
            LLMProviderCredential.agent_id == agent_id,
            LLMProviderCredential.provider == provider
        )
    )
    existing = result.scalar_one_or_none()

    encrypted = encrypt_secret(api_key)

    if existing:
        existing.encrypted_api_key = encrypted
        existing.is_active = True
        existing.last_used_at = None
        await db.commit()
        await db.refresh(existing)
        return existing

    cred = LLMProviderCredential(
        agent_id=agent_id,
        provider=provider,
        encrypted_api_key=encrypted,
        is_active=True
    )
    db.add(cred)
    await db.commit()
    await db.refresh(cred)
    return cred


async def get_active_credential(
    db: AsyncSession,
    *,
    agent_id: str,
    provider: LLMProvider
) -> LLMProviderCredential | None:
    result = await db.execute(
        select(LLMProviderCredential).where(
            LLMProviderCredential.agent_id == agent_id,
            LLMProviderCredential.provider == provider,
            LLMProviderCredential.is_active == True
        )
    )
    return result.scalar_one_or_none()


async def get_decrypted_api_key(
    db: AsyncSession,
    *,
    agent_id: str,
    provider: LLMProvider
) -> str:
    cred = await get_active_credential(db, agent_id=agent_id, provider=provider)
    if not cred:
        raise ValueError("No active credential for provider")

    cred.last_used_at = datetime.utcnow()
    await db.commit()

    return decrypt_secret(cred.encrypted_api_key)


async def list_credentials(
    db: AsyncSession,
    *,
    agent_id: str
) -> list[LLMProviderCredential]:
    result = await db.execute(
        select(LLMProviderCredential).where(LLMProviderCredential.agent_id == agent_id)
    )
    return list(result.scalars().all())


async def deactivate_credential(
    db: AsyncSession,
    *,
    agent_id: str,
    credential_id: str
) -> None:
    result = await db.execute(
        select(LLMProviderCredential).where(
            LLMProviderCredential.id == credential_id,
            LLMProviderCredential.agent_id == agent_id
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise ValueError("Credential not found")

    cred.is_active = False
    await db.commit()
