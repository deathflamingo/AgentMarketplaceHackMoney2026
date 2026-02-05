"""LLM credentials API for BYOK key management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_agent
from app.models.agent import Agent
from app.models.llm_credential import LLMProvider
from app.schemas.llm import LLMCredentialCreate, LLMCredentialResponse
from app.services.llm_credential_service import (
    upsert_credential,
    list_credentials,
    deactivate_credential
)

router = APIRouter()


@router.post("/credentials", response_model=LLMCredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_credential(
    payload: LLMCredentialCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    try:
        cred = await upsert_credential(
            db,
            agent_id=str(current_agent.id),
            provider=LLMProvider(payload.provider),
            api_key=payload.api_key
        )
        return cred
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/credentials", response_model=list[LLMCredentialResponse])
async def get_credentials(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    creds = await list_credentials(db, agent_id=str(current_agent.id))
    return creds


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    credential_id: str,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    try:
        await deactivate_credential(db, agent_id=str(current_agent.id), credential_id=credential_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
