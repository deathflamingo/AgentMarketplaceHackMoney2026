"""
Peer-to-peer negotiation service for agent price negotiations.
"""

from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.negotiation import Negotiation, NegotiationOffer
from app.models.service import Service
from app.models.agent import Agent


class P2PNegotiationService:
    """Service for peer-to-peer agent negotiation."""

    async def start_negotiation(
        self,
        db: AsyncSession,
        service_id: str,
        client_agent_id: str,
        job_description: str,
        initial_offer: Decimal,
        client_max_price: Decimal | None = None,
        message: str | None = None
    ) -> Negotiation:
        """
        Client starts a negotiation with worker.

        Args:
            service_id: Service to negotiate for
            client_agent_id: Client agent starting negotiation
            job_description: What the job entails
            initial_offer: Client's first price offer
            client_max_price: Client's maximum budget (optional)
            message: Optional message with offer

        Returns:
            Created Negotiation

        Raises:
            ValueError: If offer is outside service bounds or invalid
        """
        # Get service and worker
        result = await db.execute(select(Service).where(Service.id == service_id))
        service = result.scalar_one_or_none()

        if not service:
            raise ValueError("Service not found")

        # Validate initial offer
        if initial_offer < service.min_price_agnt:
            raise ValueError(f"Offer too low. Service minimum: {service.min_price_agnt} AGNT")

        if initial_offer > service.max_price_agnt:
            raise ValueError(f"Offer too high. Service maximum: {service.max_price_agnt} AGNT")

        if client_max_price and initial_offer > client_max_price:
            raise ValueError("Initial offer exceeds your max budget")

        # Check client has sufficient balance
        result = await db.execute(select(Agent).where(Agent.id == client_agent_id))
        client = result.scalar_one_or_none()

        if not client:
            raise ValueError("Client agent not found")

        if client.balance < initial_offer:
            raise ValueError(f"Insufficient balance. You have {client.balance} AGNT, need {initial_offer} AGNT")

        # Create negotiation
        negotiation = Negotiation(
            service_id=service_id,
            client_agent_id=client_agent_id,
            worker_agent_id=service.agent_id,
            job_description=job_description,
            status="active",
            current_price=initial_offer,
            current_proposer="client",
            service_min_price=service.min_price_agnt,
            service_max_price=service.max_price_agnt,
            client_max_price=client_max_price,
            round_count=1,
            max_rounds=5,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )

        db.add(negotiation)
        await db.flush()  # Flush to get negotiation.id

        # Create first offer
        offer = NegotiationOffer(
            negotiation_id=negotiation.id,
            agent_id=client_agent_id,
            agent_role="client",
            action="offer",
            price=initial_offer,
            message=message or f"Initial offer for: {job_description}"
        )

        db.add(offer)
        await db.commit()
        await db.refresh(negotiation, ["offers"])

        return negotiation

    async def respond_to_negotiation(
        self,
        db: AsyncSession,
        negotiation_id: str,
        agent_id: str,
        action: str,  # "accept" | "counter" | "reject"
        counter_price: Decimal | None = None,
        message: str | None = None
    ) -> Negotiation:
        """
        Respond to a negotiation offer.

        Args:
            negotiation_id: Negotiation to respond to
            agent_id: Agent responding
            action: accept, counter, or reject
            counter_price: New price if countering
            message: Optional message

        Returns:
            Updated Negotiation

        Raises:
            ValueError: If response is invalid
        """
        # Get negotiation with relationships
        result = await db.execute(
            select(Negotiation).where(Negotiation.id == negotiation_id)
        )
        negotiation = result.scalar_one_or_none()

        if not negotiation:
            raise ValueError("Negotiation not found")

        # Validate status
        if negotiation.status != "active":
            raise ValueError(f"Negotiation is {negotiation.status}, cannot respond")

        # Check expiration
        if datetime.utcnow() > negotiation.expires_at:
            negotiation.status = "expired"
            await db.commit()
            raise ValueError("Negotiation has expired")

        # Determine agent role
        if agent_id == negotiation.client_agent_id:
            agent_role = "client"
        elif agent_id == negotiation.worker_agent_id:
            agent_role = "worker"
        else:
            raise ValueError("You are not part of this negotiation")

        # Cannot respond to your own offer
        if negotiation.current_proposer == agent_role:
            raise ValueError("Waiting for other party to respond")

        # Handle action
        if action == "accept":
            # Agreement reached!
            negotiation.status = "agreed"
            negotiation.agreed_at = datetime.utcnow()
            final_price = negotiation.current_price

        elif action == "counter":
            if not counter_price:
                raise ValueError("Counter price required")

            # Validate counter is within bounds
            if counter_price < negotiation.service_min_price:
                raise ValueError(f"Counter too low. Minimum: {negotiation.service_min_price} AGNT")

            if counter_price > negotiation.service_max_price:
                raise ValueError(f"Counter too high. Maximum: {negotiation.service_max_price} AGNT")

            # Check client's max budget
            if agent_role == "client" and negotiation.client_max_price:
                if counter_price > negotiation.client_max_price:
                    raise ValueError("Counter exceeds your max budget")

            # Check client has sufficient balance for counter
            if agent_role == "client":
                result = await db.execute(select(Agent).where(Agent.id == agent_id))
                agent = result.scalar_one_or_none()
                if agent.balance < counter_price:
                    raise ValueError(f"Insufficient balance for counter offer. You have {agent.balance} AGNT, need {counter_price} AGNT")

            # Check max rounds
            negotiation.round_count += 1
            if negotiation.round_count > negotiation.max_rounds:
                negotiation.status = "rejected"
                await db.commit()
                raise ValueError(f"Maximum negotiation rounds ({negotiation.max_rounds}) reached")

            # Update negotiation
            negotiation.current_price = counter_price
            negotiation.current_proposer = agent_role
            final_price = counter_price

        elif action == "reject":
            negotiation.status = "rejected"
            final_price = negotiation.current_price

        else:
            raise ValueError(f"Invalid action: {action}. Must be 'accept', 'counter', or 'reject'")

        # Create offer record
        offer = NegotiationOffer(
            negotiation_id=negotiation_id,
            agent_id=agent_id,
            agent_role=agent_role,
            action=action,
            price=final_price,
            message=message
        )

        db.add(offer)
        await db.commit()
        await db.refresh(negotiation, ["offers"])

        return negotiation

    async def get_negotiation(
        self,
        db: AsyncSession,
        negotiation_id: str,
        agent_id: str
    ) -> Negotiation:
        """
        Get negotiation details (only if you're involved).

        Args:
            negotiation_id: Negotiation ID
            agent_id: Agent requesting details

        Returns:
            Negotiation with full history

        Raises:
            ValueError: If not found or not authorized
        """
        result = await db.execute(
            select(Negotiation)
            .options(selectinload(Negotiation.offers))
            .where(Negotiation.id == negotiation_id)
        )
        negotiation = result.scalar_one_or_none()

        if not negotiation:
            raise ValueError("Negotiation not found")

        # Verify agent is involved
        if agent_id not in [negotiation.client_agent_id, negotiation.worker_agent_id]:
            raise ValueError("You are not authorized to view this negotiation")

        return negotiation

    async def list_my_negotiations(
        self,
        db: AsyncSession,
        agent_id: str,
        status_filter: str | None = None
    ) -> list[Negotiation]:
        """
        List all negotiations where agent is involved.

        Args:
            agent_id: Agent ID
            status_filter: Optional status filter (active, agreed, rejected, expired)

        Returns:
            List of negotiations
        """
        query = select(Negotiation).options(
            selectinload(Negotiation.offers)
        ).where(
            (Negotiation.client_agent_id == agent_id) |
            (Negotiation.worker_agent_id == agent_id)
        )

        if status_filter:
            query = query.where(Negotiation.status == status_filter)

        query = query.order_by(Negotiation.created_at.desc())

        result = await db.execute(query)
        negotiations = result.scalars().all()

        return list(negotiations)


# Singleton
p2p_negotiation_service = P2PNegotiationService()
