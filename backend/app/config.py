"""Application configuration management using Pydantic Settings."""

from typing import List
from decimal import Decimal
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str

    # API
    API_V1_PREFIX: str = "/api"

    # CORS
    CORS_ORIGINS: List[str] = ['http://localhost:3000']

    # Environment
    ENVIRONMENT: str = "development"

    # Blockchain & Payment Settings
    WEB3_RPC_URL: str = "https://sepolia.base.org"
    USDC_ADDRESS: str = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"  # Base Sepolia USDC
    PLATFORM_WALLET_ADDRESS: str = "0x0000000000000000000000000000000000000000"  # Set in production
    MIN_CONFIRMATIONS: int = 1  # Minimum block confirmations for payment verification
    PAYMENT_VERIFICATION_TIMEOUT: int = 300  # Seconds to wait for transaction verification

    # AgentCoin Token
    AGENTCOIN_ADDRESS: str = "0x0000000000000000000000000000000000000000"  # Set after deployment
    AGENTCOIN_DECIMALS: int = 18

    # Conversion Rate
    USDC_TO_AGNT_RATE: Decimal = Decimal("10000")  # 1 USDC = 10,000 AGNT

    # Uniswap V4 Integration
    UNISWAP_V4_POOL_MANAGER: str = "0x0000000000000000000000000000000000000000"  # Set after pool setup
    UNISWAP_V4_UNIVERSAL_ROUTER: str = "0x0000000000000000000000000000000000000000"  # Uniswap V4 Universal Router
    UNISWAP_V4_POSITION_MANAGER: str = "0x0000000000000000000000000000000000000000"  # Uniswap V4 Position Manager
    UNISWAP_V4_QUOTER: str = "0x0000000000000000000000000000000000000000"  # Uniswap V4 Quoter
    AGNT_USDC_POOL_ID: str = ""  # Pool identifier in Uniswap V4
    SWAP_SLIPPAGE_TOLERANCE: Decimal = Decimal("0.02")  # 2% max slippage

    # Withdrawal Settings
    WITHDRAWAL_MIN_AMOUNT: Decimal = Decimal("100000")  # Min 100k AGNT (~10 USDC)
    WITHDRAWAL_FEE_PERCENT: Decimal = Decimal("0.5")  # 0.5% fee to cover gas
    WITHDRAWAL_RATE_LIMIT_PER_HOUR: int = 3  # Max withdrawals per agent per hour
    PLATFORM_WALLET_PRIVATE_KEY: str = ""  # For executing withdrawals (SECURE! Use vault in production)

    # Price Negotiation Settings
    NEGOTIATION_LLM_API_KEY: str = ""  # Claude API key for price negotiation
    NEGOTIATION_LLM_MODEL: str = "claude-sonnet-4-5-20250929"  # Claude model for negotiation
    QUOTE_EXPIRATION_SECONDS: int = 3600  # Quotes valid for 1 hour
    ENABLE_PRICE_NEGOTIATION: bool = True  # Feature flag for negotiation

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v) -> List[str]:
        """Parse CORS_ORIGINS from JSON string to list."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("USDC_TO_AGNT_RATE", "SWAP_SLIPPAGE_TOLERANCE", "WITHDRAWAL_MIN_AMOUNT", "WITHDRAWAL_FEE_PERCENT", mode="before")
    @classmethod
    def parse_decimal(cls, v) -> Decimal:
        """Parse string to Decimal for precise arithmetic."""
        if isinstance(v, str):
            return Decimal(v)
        return v


# Global settings instance
settings = Settings()
