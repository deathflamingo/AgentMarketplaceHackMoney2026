"""LLM-based price negotiation service using Claude API."""

import logging
import json
from decimal import Decimal
from typing import Optional
import anthropic

from app.config import settings
from app.models.service import Service
from app.models.agent import Agent

logger = logging.getLogger(__name__)


class NegotiationService:
    """Service for LLM-powered price negotiation."""

    def __init__(self):
        self.api_key = settings.NEGOTIATION_LLM_API_KEY
        self.model = settings.NEGOTIATION_LLM_MODEL
        self.enabled = settings.ENABLE_PRICE_NEGOTIATION

        if self.api_key and self.enabled:
            self.client = anthropic.Anthropic(api_key=self.api_key)
        else:
            self.client = None
            logger.warning("Price negotiation disabled or API key not configured")

    async def negotiate_price(
        self,
        service: Service,
        job_description: str,
        client_max_price: Optional[Decimal],
        client_agent: Agent
    ) -> Decimal:
        """
        Use Claude to negotiate a fair price within service bounds.

        Args:
            service: The service being hired
            job_description: Description of the job/task
            client_max_price: Client's maximum budget (None = no constraint)
            client_agent: The agent requesting the service

        Returns:
            Negotiated price in AGNT

        Raises:
            ValueError: If negotiation fails or client budget too low
        """
        # If negotiation disabled, return midpoint price
        if not self.enabled or not self.client:
            midpoint = (service.min_price_agnt + service.max_price_agnt) / Decimal("2")
            logger.info(f"Negotiation disabled, using midpoint price: {midpoint} AGNT")
            return midpoint

        # If service doesn't allow negotiation, return fixed price (midpoint)
        if not service.allow_negotiation:
            fixed_price = (service.min_price_agnt + service.max_price_agnt) / Decimal("2")
            logger.info(f"Service negotiation disabled, using fixed price: {fixed_price} AGNT")
            return fixed_price

        try:
            logger.info(
                f"Negotiating price for service {service.id}: "
                f"range [{service.min_price_agnt}, {service.max_price_agnt}], "
                f"client max: {client_max_price}"
            )

            # Build negotiation prompt
            prompt = self._build_negotiation_prompt(
                service,
                job_description,
                client_max_price,
                client_agent
            )

            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=150,
                temperature=0.3,  # Lower temperature for more consistent pricing
                messages=[{"role": "user", "content": prompt}]
            )

            # Extract price from response
            suggested_price = self._extract_price(response.content[0].text)

            # Validate and clamp price within bounds
            final_price = self._validate_price(
                suggested_price,
                service.min_price_agnt,
                service.max_price_agnt,
                client_max_price
            )

            logger.info(
                f"Price negotiated: {final_price} AGNT "
                f"(suggested: {suggested_price}, clamped to bounds)"
            )

            return final_price

        except Exception as e:
            logger.error(f"Error during price negotiation: {e}", exc_info=True)
            # Fallback to midpoint on error
            fallback_price = (service.min_price_agnt + service.max_price_agnt) / Decimal("2")
            logger.warning(f"Using fallback midpoint price: {fallback_price} AGNT")
            return fallback_price

    def _build_negotiation_prompt(
        self,
        service: Service,
        job_description: str,
        client_max_price: Optional[Decimal],
        client_agent: Agent
    ) -> str:
        """Construct the negotiation prompt for Claude."""

        # Calculate USD equivalents for context
        usdc_rate = settings.USDC_TO_AGNT_RATE
        min_price_usd = float(service.min_price_agnt / usdc_rate)
        max_price_usd = float(service.max_price_agnt / usdc_rate)
        client_max_usd = float(client_max_price / usdc_rate) if client_max_price else None

        # Build client context
        client_context = f"""
Client Information:
- Reputation Score: {float(client_agent.reputation_score):.2f}/5.00
- Jobs Completed: {client_agent.jobs_completed}
- Jobs Hired: {client_agent.jobs_hired}
- Success Rate: {(client_agent.jobs_completed / max(client_agent.jobs_hired, 1)) * 100:.1f}%
"""

        # Build budget constraint
        budget_constraint = ""
        if client_max_price:
            budget_constraint = f"\n- Client's Maximum Budget: {int(client_max_price):,} AGNT (~${client_max_usd:.2f} USD)"

        prompt = f"""You are a fair price negotiator for an AI agent marketplace. Your job is to suggest a reasonable price for a service based on multiple factors.

Service Information:
- Name: {service.name}
- Description: {service.description}
- Price Range: {int(service.min_price_agnt):,} - {int(service.max_price_agnt):,} AGNT (~${min_price_usd:.2f} - ${max_price_usd:.2f} USD)
- Estimated Duration: {service.estimated_minutes or 'Not specified'} minutes

Job Request:
{job_description}

{client_context}{budget_constraint}

Task Complexity Analysis:
Analyze the job description to estimate:
1. Complexity level (simple, moderate, complex)
2. Required effort and resources
3. Any special requirements or challenges

Pricing Factors:
1. Task complexity (higher complexity = higher price)
2. Client reputation (better reputation = slight discount as preferred customer)
3. Service price range (must stay within bounds)
4. Client budget constraint (must not exceed if specified)
5. Fair market value

Instructions:
- Suggest a fair price in AGNT tokens that:
  * Falls within the service's min/max range
  * Reflects task complexity
  * Respects client budget constraints
  * Considers client reputation (max 5% discount for excellent reputation)
- Return ONLY a number (the price in AGNT), nothing else
- Do not include explanations, currency symbols, or commas
- Example valid responses: "125000" or "87500"

Suggested Price (AGNT only):"""

        return prompt

    def _extract_price(self, response_text: str) -> Decimal:
        """Extract price number from Claude's response."""
        try:
            # Remove any whitespace and common formatting
            cleaned = response_text.strip()
            cleaned = cleaned.replace(',', '').replace(' ', '')
            cleaned = cleaned.replace('AGNT', '').replace('agnt', '')

            # Try to extract first number
            import re
            match = re.search(r'(\d+(?:\.\d+)?)', cleaned)
            if match:
                price = Decimal(match.group(1))
                return price
            else:
                raise ValueError(f"No number found in response: {response_text}")

        except Exception as e:
            logger.error(f"Error extracting price from response '{response_text}': {e}")
            raise ValueError(f"Could not parse price from LLM response: {response_text}")

    def _validate_price(
        self,
        suggested_price: Decimal,
        min_price: Decimal,
        max_price: Decimal,
        client_max_price: Optional[Decimal]
    ) -> Decimal:
        """
        Validate and clamp price within bounds.

        Args:
            suggested_price: LLM-suggested price
            min_price: Service minimum price
            max_price: Service maximum price
            client_max_price: Client's budget constraint

        Returns:
            Valid price within all constraints

        Raises:
            ValueError: If client budget is below service minimum
        """
        # Check if client budget is feasible
        if client_max_price and client_max_price < min_price:
            raise ValueError(
                f"Client budget ({client_max_price} AGNT) is below service minimum "
                f"({min_price} AGNT). Cannot negotiate."
            )

        # Clamp to service bounds
        clamped_price = max(min_price, min(max_price, suggested_price))

        # Further clamp to client budget if specified
        if client_max_price:
            clamped_price = min(clamped_price, client_max_price)

        return clamped_price

    def build_negotiation_factors(
        self,
        service: Service,
        job_description: str,
        client_agent: Agent,
        final_price: Decimal
    ) -> str:
        """
        Build a JSON string documenting factors considered in negotiation.

        Returns JSON string for storage in price_quote.negotiation_factors
        """
        factors = {
            "job_complexity": "analyzed from description",
            "client_reputation": float(client_agent.reputation_score),
            "client_jobs_completed": client_agent.jobs_completed,
            "service_min_price": float(service.min_price_agnt),
            "service_max_price": float(service.max_price_agnt),
            "final_price": float(final_price),
            "price_position": float((final_price - service.min_price_agnt) / (service.max_price_agnt - service.min_price_agnt)) if service.max_price_agnt > service.min_price_agnt else 0.5
        }

        return json.dumps(factors)


# Singleton instance
negotiation_service = NegotiationService()
