"""x402 Payment Required middleware and utilities."""

from decimal import Decimal
from typing import Optional
from fastapi import Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.services.payment_service import payment_service
from app.services.chain_service import chain_service


class PaymentRequiredException(Exception):
    """Exception raised when payment is required (x402)."""

    def __init__(
        self,
        amount: Decimal,
        recipient_address: str,
        currency: str = "USDC",
        service_id: Optional[str] = None,
        message: str = "Payment required to access this service"
    ):
        self.amount = amount
        self.recipient_address = recipient_address
        self.currency = currency
        self.service_id = service_id
        self.message = message
        super().__init__(self.message)


def create_x402_response(
    amount: Decimal,
    recipient_address: str,
    currency: str = "USDC",
    chain_id: str = "84532",  # Base Sepolia
    token_address: str = "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # USDC on Base Sepolia
    message: str = "Payment required to access this service"
) -> JSONResponse:
    """
    Create an x402 Payment Required response with proper headers.

    Following the x402 standard from Coinbase CDP:
    https://docs.cdp.coinbase.com/x402/welcome
    """
    metadata = payment_service.generate_payment_metadata(
        amount=amount,
        currency=currency,
        recipient_address=recipient_address
    )

    headers = {
        "x402-price": str(amount),
        "x402-currency": currency,
        "x402-recipient": recipient_address,
        "x402-chain-id": chain_id,
        "x402-token-address": token_address,
        "x402-expiration": metadata["x402-expiration"],
    }

    body = {
        "error": "payment_required",
        "message": message,
        "payment": {
            "amount": str(amount),
            "currency": currency,
            "recipient": recipient_address,
            "chain_id": chain_id,
            "token_address": token_address,
            "expiration": metadata["x402-expiration"]
        }
    }

    return JSONResponse(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        content=body,
        headers=headers
    )


async def verify_x402_payment(
    tx_hash: str,
    expected_amount: Decimal,
    recipient_address: str,
    token_address: Optional[str] = None
) -> bool:
    """
    Verify x402 payment proof (transaction hash).

    Args:
        tx_hash: Transaction hash from x402-payment-proof header
        expected_amount: Expected payment amount
        recipient_address: Expected recipient (worker's wallet)
        token_address: Optional token contract address

    Returns:
        True if payment is valid, False otherwise
    """
    return chain_service.verify_transaction(
        tx_hash=tx_hash,
        expected_amount=expected_amount,
        recipient_address=recipient_address,
        token_address=token_address
    )


def parse_x402_payment_proof(
    x402_payment_proof: Optional[str] = Header(None, alias="x402-payment-proof")
) -> Optional[str]:
    """
    Dependency to extract x402-payment-proof header.

    Usage in endpoint:
        payment_proof: Optional[str] = Depends(parse_x402_payment_proof)
    """
    return x402_payment_proof
