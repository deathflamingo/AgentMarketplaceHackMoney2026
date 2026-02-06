"""Uniswap V4 service for token swaps and price quotes."""

import logging
from decimal import Decimal
from typing import Dict, Optional
from web3 import Web3
from web3.exceptions import TransactionNotFound

from app.config import settings

logger = logging.getLogger(__name__)


class UniswapV4Service:
    """Service for interacting with Uniswap V4 pools."""

    def __init__(self):
        self.web3 = Web3(Web3.HTTPProvider(settings.WEB3_RPC_URL))
        self.pool_manager_address = settings.UNISWAP_V4_POOL_MANAGER
        self.pool_id = settings.AGNT_USDC_POOL_ID
        self.agnt_address = settings.AGENTCOIN_ADDRESS
        self.usdc_address = settings.USDC_ADDRESS
        self.slippage_tolerance = settings.SWAP_SLIPPAGE_TOLERANCE

        # Minimal ABI for Uniswap V4 PoolManager
        # Note: This is a simplified ABI. Update with actual Uniswap V4 ABI after deployment
        self.pool_manager_abi = [
            {
                "inputs": [
                    {"name": "poolId", "type": "bytes32"},
                ],
                "name": "getSlot0",
                "outputs": [
                    {"name": "sqrtPriceX96", "type": "uint160"},
                    {"name": "tick", "type": "int24"},
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]

        # ERC20 ABI for token transfers
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
                "stateMutability": "view",
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [{"name": "account", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]

    async def get_quote_usdc_to_agnt(self, usdc_amount: Decimal) -> Decimal:
        """
        Get expected AGNT output for USDC input.

        Args:
            usdc_amount: Amount of USDC to swap (in human-readable units, e.g., 10.5)

        Returns:
            Expected AGNT amount received (accounting for slippage)
        """
        try:
            # For now, use the static conversion rate from config
            # TODO: Replace with actual Uniswap pool price query
            base_rate = settings.USDC_TO_AGNT_RATE
            agnt_amount = usdc_amount * base_rate

            # Apply slippage tolerance (reduce by slippage %)
            agnt_amount_with_slippage = agnt_amount * (Decimal("1") - self.slippage_tolerance)

            logger.info(
                f"Quote: {usdc_amount} USDC → {agnt_amount_with_slippage} AGNT "
                f"(rate: {base_rate}, slippage: {self.slippage_tolerance * 100}%)"
            )

            return agnt_amount_with_slippage

        except Exception as e:
            logger.error(f"Error getting USDC→AGNT quote: {e}", exc_info=True)
            raise

    async def get_quote_agnt_to_usdc(self, agnt_amount: Decimal) -> Decimal:
        """
        Get expected USDC output for AGNT input.

        Args:
            agnt_amount: Amount of AGNT to swap (in human-readable units)

        Returns:
            Expected USDC amount received (accounting for slippage)
        """
        try:
            # For now, use the static conversion rate from config
            # TODO: Replace with actual Uniswap pool price query
            base_rate = Decimal("1") / settings.USDC_TO_AGNT_RATE
            usdc_amount = agnt_amount * base_rate

            # Apply slippage tolerance (reduce by slippage %)
            usdc_amount_with_slippage = usdc_amount * (Decimal("1") - self.slippage_tolerance)

            logger.info(
                f"Quote: {agnt_amount} AGNT → {usdc_amount_with_slippage} USDC "
                f"(rate: {base_rate}, slippage: {self.slippage_tolerance * 100}%)"
            )

            return usdc_amount_with_slippage

        except Exception as e:
            logger.error(f"Error getting AGNT→USDC quote: {e}", exc_info=True)
            raise

    async def verify_swap_transaction(
        self,
        tx_hash: str,
        expected_token_out: str,
        min_amount_out: Decimal
    ) -> Dict:
        """
        Verify that a swap transaction occurred and extract amounts.

        Args:
            tx_hash: Transaction hash to verify
            expected_token_out: Expected output token address (AGNT or USDC)
            min_amount_out: Minimum expected amount out (after slippage)

        Returns:
            Dictionary with swap details:
            {
                'success': bool,
                'token_in': str,
                'token_out': str,
                'amount_in': Decimal,
                'amount_out': Decimal,
                'recipient': str,
                'exchange_rate': Decimal
            }

        Raises:
            ValueError: If transaction invalid or amounts don't meet minimum
        """
        try:
            logger.info(
                f"Verifying swap transaction: tx_hash={tx_hash}, "
                f"expected_token_out={expected_token_out}, min_amount_out={min_amount_out}"
            )

            # Get transaction receipt
            receipt = self.web3.eth.get_transaction_receipt(tx_hash)

            if not receipt:
                raise ValueError(f"Transaction not found: {tx_hash}")

            if receipt['status'] != 1:
                raise ValueError(f"Transaction failed on-chain: {tx_hash}")

            # Parse Transfer events for both tokens
            token_transfers = self._parse_transfer_events(receipt)

            if not token_transfers:
                raise ValueError(f"No token transfers found in transaction {tx_hash}")

            # Find the swap (should have transfers for both USDC and AGNT)
            swap_details = self._extract_swap_details(
                token_transfers,
                expected_token_out,
                min_amount_out
            )

            logger.info(
                f"Swap verified: {swap_details['amount_in']} {swap_details['token_in']} → "
                f"{swap_details['amount_out']} {swap_details['token_out']}"
            )

            return swap_details

        except TransactionNotFound:
            logger.error(f"Transaction not found: {tx_hash}")
            raise ValueError(f"Transaction not found: {tx_hash}")
        except Exception as e:
            logger.error(f"Error verifying swap transaction {tx_hash}: {e}", exc_info=True)
            raise

    def _parse_transfer_events(self, receipt) -> list:
        """Parse Transfer events from transaction receipt."""
        transfers = []

        # Parse USDC transfers
        usdc_contract = self.web3.eth.contract(
            address=self.usdc_address,
            abi=self.erc20_abi
        )
        usdc_decimals = usdc_contract.functions.decimals().call()

        # Parse AGNT transfers
        agnt_contract = self.web3.eth.contract(
            address=self.agnt_address,
            abi=self.erc20_abi
        )
        agnt_decimals = agnt_contract.functions.decimals().call()

        # Process all logs
        for log in receipt['logs']:
            # Check if this is a Transfer event
            if len(log['topics']) < 3:
                continue

            # Transfer event signature
            transfer_sig = self.web3.keccak(text='Transfer(address,address,uint256)')
            if log['topics'][0] != transfer_sig:
                continue

            # Get token address
            token_address = log['address']

            # Decode transfer
            from_addr = '0x' + log['topics'][1].hex()[-40:]
            to_addr = '0x' + log['topics'][2].hex()[-40:]
            value = int(log['data'].hex(), 16)

            # Determine token symbol and decimals
            if token_address.lower() == self.usdc_address.lower():
                symbol = 'USDC'
                decimals = usdc_decimals
            elif token_address.lower() == self.agnt_address.lower():
                symbol = 'AGNT'
                decimals = agnt_decimals
            else:
                continue  # Skip other tokens

            # Convert to human-readable amount
            amount = Decimal(value) / Decimal(10 ** decimals)

            transfers.append({
                'token': token_address,
                'symbol': symbol,
                'from': from_addr,
                'to': to_addr,
                'amount': amount
            })

        return transfers

    def _extract_swap_details(
        self,
        transfers: list,
        expected_token_out: str,
        min_amount_out: Decimal
    ) -> Dict:
        """Extract swap details from transfer events."""

        # Find the output transfer (token being received)
        output_transfer = None
        for transfer in transfers:
            if transfer['token'].lower() == expected_token_out.lower():
                output_transfer = transfer
                break

        if not output_transfer:
            raise ValueError(f"No transfer found for expected output token: {expected_token_out}")

        # Verify minimum amount
        if output_transfer['amount'] < min_amount_out:
            raise ValueError(
                f"Output amount {output_transfer['amount']} below minimum {min_amount_out}"
            )

        # Find the corresponding input transfer
        # (The other token in the pair)
        input_transfer = None
        for transfer in transfers:
            if transfer['token'].lower() != expected_token_out.lower():
                if transfer['symbol'] in ['USDC', 'AGNT']:
                    input_transfer = transfer
                    break

        if not input_transfer:
            # If we can't find input, just use output info
            logger.warning("Could not find input transfer, using output only")
            return {
                'success': True,
                'token_in': 'UNKNOWN',
                'token_out': output_transfer['symbol'],
                'amount_in': Decimal("0"),
                'amount_out': output_transfer['amount'],
                'recipient': output_transfer['to'],
                'exchange_rate': Decimal("0")
            }

        # Calculate exchange rate
        exchange_rate = output_transfer['amount'] / input_transfer['amount'] if input_transfer['amount'] > 0 else Decimal("0")

        return {
            'success': True,
            'token_in': input_transfer['symbol'],
            'token_out': output_transfer['symbol'],
            'amount_in': input_transfer['amount'],
            'amount_out': output_transfer['amount'],
            'recipient': output_transfer['to'],
            'exchange_rate': exchange_rate
        }


# Singleton instance
uniswap_service = UniswapV4Service()
