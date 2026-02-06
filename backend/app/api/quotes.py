"""Price quote API endpoints."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_agent
from app.models.agent import Agent
from app.models.service import Service
from app.models.price_quote import PriceQuote
from app.schemas.quote import QuoteRequest, QuoteResponse, QuoteCreateResponse
from app.services.negotiation_service import negotiation_service
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.post("/request", response_model=QuoteCreateResponse, status_code=status.HTTP_201_CREATED)
async def request_quote(
    request: QuoteRequest,
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Request a price quote for a service with LLM-based negotiation.

    The negotiation considers:
    - Job complexity (from description)
    - Service price range
    - Client budget constraint
    - Client reputation score
    - Historical job completion rate

    Args:
        request: Quote request with service ID, job description, and optional max price
        db: Database session
        current_agent: Authenticated agent

    Returns:
        Price quote with negotiated price valid for 1 hour

    Raises:
        404: Service not found or inactive
        400: Client budget below service minimum
        500: Internal error during negotiation
    """
    try:
        logger.info(
            f"Agent {current_agent.id} requesting quote for service {request.service_id}"
        )

        # 1. Fetch service
        result = await db.execute(
            select(Service).where(Service.id == request.service_id)
        )
        service = result.scalar_one_or_none()

        if not service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service {request.service_id} not found"
            )

        if not service.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Service is not currently active"
            )

        # 2. Check if client budget is feasible (if provided)
        if request.max_price_willing and request.max_price_willing < service.min_price_agnt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Your budget ({request.max_price_willing} AGNT) is below "
                    f"service minimum ({service.min_price_agnt} AGNT)"
                )
            )

        # 3. Negotiate price using LLM
        try:
            quoted_price = await negotiation_service.negotiate_price(
                service=service,
                job_description=request.job_description,
                client_max_price=request.max_price_willing,
                client_agent=current_agent
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except Exception as e:
            logger.error(f"Error during price negotiation: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error negotiating price. Please try again."
            )

        # 4. Build negotiation factors
        negotiation_factors = negotiation_service.build_negotiation_factors(
            service=service,
            job_description=request.job_description,
            client_agent=current_agent,
            final_price=quoted_price
        )

        # 5. Create quote record
        quote_expiration = datetime.utcnow() + timedelta(
            seconds=settings.QUOTE_EXPIRATION_SECONDS
        )

        quote = PriceQuote(
            id=str(uuid.uuid4()),
            service_id=service.id,
            client_agent_id=current_agent.id,
            job_description=request.job_description,
            max_price_willing=request.max_price_willing or service.max_price_agnt,
            quoted_price=quoted_price,
            service_min_price=service.min_price_agnt,
            service_max_price=service.max_price_agnt,
            negotiation_factors=negotiation_factors,
            status="pending",
            created_at=datetime.utcnow(),
            valid_until=quote_expiration
        )

        db.add(quote)
        await db.commit()
        await db.refresh(quote)

        logger.info(
            f"✅ Quote created: {quote.id}, price: {quoted_price} AGNT "
            f"(range: {service.min_price_agnt}-{service.max_price_agnt})"
        )

        # Enrich response with USD equivalent
        quote_response = QuoteResponse.model_validate(quote)
        quote_response.quoted_price_usd = quoted_price / settings.USDC_TO_AGNT_RATE

        # Calculate savings vs max price
        if service.max_price_agnt > service.min_price_agnt:
            savings = (service.max_price_agnt - quoted_price) / service.max_price_agnt * Decimal("100")
            quote_response.savings_percent = savings
        else:
            quote_response.savings_percent = Decimal("0")

        return QuoteCreateResponse(
            success=True,
            message=f"Price negotiated: {quoted_price} AGNT (${quote_response.quoted_price_usd:.2f} USD)",
            quote=quote_response,
            expires_in_seconds=settings.QUOTE_EXPIRATION_SECONDS
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating quote: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error creating quote"
        )


@router.get("/history", response_model=list[QuoteResponse])
async def get_quote_history(
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
    limit: int = 50,
    offset: int = 0,
    status_filter: str | None = None
):
    """
    Get quote request history for the current agent.

    Args:
        db: Database session
        current_agent: Authenticated agent
        limit: Maximum number of quotes to return
        offset: Number of quotes to skip
        status_filter: Optional filter by status (pending/accepted/expired/rejected)

    Returns:
        List of price quotes
    """
    query = select(PriceQuote).where(
        PriceQuote.client_agent_id == current_agent.id
    )

    if status_filter:
        query = query.where(PriceQuote.status == status_filter)

    query = query.order_by(PriceQuote.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    quotes = result.scalars().all()

    # Enrich with USD prices
    quote_responses = []
    for quote in quotes:
        quote_resp = QuoteResponse.model_validate(quote)
        quote_resp.quoted_price_usd = quote.quoted_price / settings.USDC_TO_AGNT_RATE
        quote_responses.append(quote_resp)

    return quote_responses


@router.get("/{quote_id}", response_model=QuoteResponse)
async def get_quote(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Get details of a specific quote.

    Args:
        quote_id: Quote ID
        db: Database session
        current_agent: Authenticated agent

    Returns:
        Quote details

    Raises:
        404: Quote not found
    """
    result = await db.execute(
        select(PriceQuote).where(
            PriceQuote.id == quote_id,
            PriceQuote.client_agent_id == current_agent.id
        )
    )
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found"
        )

    # Enrich with USD price
    quote_response = QuoteResponse.model_validate(quote)
    quote_response.quoted_price_usd = quote.quoted_price / settings.USDC_TO_AGNT_RATE

    return quote_response


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_quote(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Cancel/reject a pending quote.

    Args:
        quote_id: Quote ID
        db: Database session
        current_agent: Authenticated agent

    Raises:
        404: Quote not found
        400: Quote already accepted or expired
    """
    result = await db.execute(
        select(PriceQuote).where(
            PriceQuote.id == quote_id,
            PriceQuote.client_agent_id == current_agent.id
        )
    )
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found"
        )

    if quote.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel quote with status: {quote.status}"
        )

    quote.status = "rejected"
    await db.commit()

    logger.info(f"Quote {quote_id} cancelled by agent {current_agent.id}")
