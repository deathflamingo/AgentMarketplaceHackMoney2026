"""Chain service for interacting with blockchain networks."""

import os
import logging
from decimal import Decimal
from typing import Optional
from web3 import Web3
from web3.exceptions import TransactionNotFound

logger = logging.getLogger(__name__)

class ChainService:
    def __init__(self):
        self.rpc_url = os.getenv("WEB3_RPC_URL", "https://sepolia.base.org")
        self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.usdc_address = os.getenv("USDC_ADDRESS", "0x036CbD53842c5426634e7929541eC2318f3dCF7e") # Base Sepolia USDC
        
        # Reduced ABI for Transfer events and decimals
        self.erc20_abi = [
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "name": "from", "type": "address"},
                    {"indexed": True, "name": "to", "type": "address"},
                    {"indexed": False, "name": "value", "type": "uint256"}
                ],
                "name": "Transfer",
                "type": "event"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
    def verify_transaction(
        self,
        tx_hash: str,
        expected_amount: Decimal,
        recipient_address: str,
        token_address: Optional[str] = None
    ) -> bool:
        """
        Verify a transaction on chain.

        Args:
            tx_hash: Transaction hash string
            expected_amount: Expected amount (in human readable units, e.g. 10.5 USDC)
            recipient_address: Expected recipient wallet address
            token_address: Optional token contract address (defaults to USDC env var)

        Returns:
            True if valid and confirmed
        """
        try:
            logger.info(
                f"Verifying transaction: tx_hash={tx_hash}, "
                f"expected_amount={expected_amount}, recipient={recipient_address}"
            )

            # 1. Get Transaction Receipt
            receipt = self.web3.eth.get_transaction_receipt(tx_hash)

            if not receipt:
                logger.warning(f"Transaction receipt not found for tx_hash={tx_hash}")
                return False

            if receipt['status'] != 1:
                logger.warning(f"Transaction failed on-chain: tx_hash={tx_hash}, status={receipt['status']}")
                return False  # Transaction failed

            # 2. Check for Token Transfer
            target_token = token_address or self.usdc_address
            contract = self.web3.eth.contract(address=target_token, abi=self.erc20_abi)

            # Parse logs for Transfer events
            transfers = contract.events.Transfer().process_receipt(receipt)

            if not transfers:
                logger.warning(f"No Transfer events found in transaction {tx_hash}")
                return False

            logger.info(f"Found {len(transfers)} Transfer events in transaction {tx_hash}")

            for event in transfers:
                args = event['args']

                # Check recipient
                if args['to'].lower() != recipient_address.lower():
                    logger.debug(
                        f"Recipient mismatch: expected={recipient_address.lower()}, "
                        f"got={args['to'].lower()}"
                    )
                    continue

                # Check amount
                # We need decimals to convert
                decimals = contract.functions.decimals().call()
                amount_wei = args['value']
                amount_human = Decimal(amount_wei) / Decimal(10 ** decimals)

                logger.info(
                    f"Comparing amounts: expected={expected_amount}, "
                    f"actual={amount_human}, decimals={decimals}"
                )

                # Allow small implementation diff (epsilon) if needed, but exact match preferred
                if amount_human == expected_amount:
                    logger.info(f"Transaction verification successful for {tx_hash}")
                    return True
                else:
                    logger.warning(
                        f"Amount mismatch: expected={expected_amount}, actual={amount_human}"
                    )

            logger.warning(f"No matching Transfer event found for tx_hash={tx_hash}")
            return False

        except TransactionNotFound:
            logger.warning(f"Transaction not found on blockchain: {tx_hash}")
            return False
        except Exception as e:
            logger.error(f"Error verifying transaction {tx_hash}: {e}", exc_info=True)
            return False

# Singleton instance
chain_service = ChainService()
