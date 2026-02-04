"""Payment service implementing x402 protocol basics."""

from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from app.config import settings

class PaymentService:
    @staticmethod
    def generate_payment_metadata(
        amount: Decimal,
        currency: str = "USDC",
        recipient_address: str = None,
        timeout_seconds: int = 3600
    ) -> Dict[str, Any]:
        """
        Generate x402 compatible payment metadata.
        
        Args:
            amount: Amount to request
            currency: Currency code (default: USDC)
            recipient_address: Wallet address to receive payment
            timeout_seconds: Expiration time for this payment request
            
        Returns:
            Dictionary containing x402 headers/body data
        """
        # Default to a platform wallet if specific recipient not provided
        # In a real app, this should come from config or the specific agent
        target_address = recipient_address or "0x0000000000000000000000000000000000000000"
        
        expiration = datetime.utcnow() + timedelta(seconds=timeout_seconds)
        
        return {
            "x402-price": str(amount),
            "x402-currency": currency,
            "x402-recipient": target_address,
            "x402-expiration": expiration.isoformat(),
            # Additional metadata for client convenience
            "chain_id": "84532",  # Base Sepolia testnet
            "token_address": settings.USDC_ADDRESS,  # USDC from config
        }

    @staticmethod
    async def verify_transaction(tx_hash: str, expected_amount: Decimal, recipient: str) -> bool:
        """
        Verify a blockchain transaction.
        
        Args:
            tx_hash: Transaction hash to verify
            expected_amount: Amount that should have been transferred
            recipient: Expected recipient address
            
        Returns:
            True if valid, False otherwise
        """
        # TODO: Implement actual RPC call to check transaction
        # For now, we trust the client (Stub)
        if not tx_hash or len(tx_hash) < 10:
            return False
            
        return True

payment_service = PaymentService()
