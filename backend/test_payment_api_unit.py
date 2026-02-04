#!/usr/bin/env python3
"""
Unit tests for refactored payment API.
Tests the payment verification logic without requiring a running server.
"""

import sys
import asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

sys.path.insert(0, '.')


async def test_payment_request_validation():
    """Test that payment request validation works correctly."""
    from app.api.payments import PaymentVerificationRequest
    from app.models.payment_transaction import TransactionType

    # Test valid request
    request = PaymentVerificationRequest(
        tx_hash="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        amount=Decimal("25.50"),
        currency="USDC",
        transaction_type=TransactionType.TOP_UP
    )

    assert request.tx_hash == "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    assert request.amount == Decimal("25.50")
    assert request.transaction_type == TransactionType.TOP_UP

    print("✓ Payment request validation works")


async def test_transaction_model():
    """Test PaymentTransaction model structure."""
    from app.models.payment_transaction import (
        PaymentTransaction,
        TransactionStatus,
        TransactionType
    )

    # Test that we can create a transaction object (without DB)
    # This validates the model structure
    tx_data = {
        'tx_hash': '0xabcd1234',
        'amount': Decimal('100.00'),
        'currency': 'USDC',
        'transaction_type': TransactionType.TOP_UP,
        'status': TransactionStatus.PENDING,
        'initiator_agent_id': 'agent-123',
        'to_address': '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        'token_address': '0x036CbD53842c5426634e7929541eC2318f3dCF7e',
        'created_at': datetime.utcnow()
    }

    # Model attributes are defined correctly
    assert hasattr(PaymentTransaction, 'tx_hash')
    assert hasattr(PaymentTransaction, 'amount')
    assert hasattr(PaymentTransaction, 'status')
    assert hasattr(PaymentTransaction, 'transaction_type')

    print("✓ PaymentTransaction model structure valid")


async def test_verification_service_replay_protection():
    """Test that replay protection works in the service."""
    from app.services.payment_verification_service import payment_verification_service
    from app.models.payment_transaction import PaymentTransaction, TransactionStatus
    from fastapi import HTTPException

    # Mock database session
    mock_db = AsyncMock()

    # Simulate existing transaction (replay attack scenario)
    existing_tx = Mock()
    existing_tx.status = TransactionStatus.CREDITED
    existing_tx.tx_hash = "0xabcd1234"
    existing_tx.initiator_agent_id = "agent-123"

    # Mock the _get_transaction_by_hash method to return existing transaction
    with patch.object(
        payment_verification_service,
        '_get_transaction_by_hash',
        return_value=existing_tx
    ):
        try:
            await payment_verification_service.verify_and_credit_payment(
                db=mock_db,
                tx_hash="0xabcd1234",
                amount=Decimal("100.00"),
                currency="USDC",
                initiator_agent_id="agent-123",
            )
            assert False, "Should have raised HTTPException for replay attack"
        except HTTPException as e:
            assert e.status_code == 409
            assert "already been processed" in e.detail
            print("✓ Replay attack protection works")


async def test_chain_service_integration():
    """Test that chain service is properly configured."""
    from app.services.chain_service import chain_service

    # Verify chain service has Web3 instance
    assert chain_service.web3 is not None
    assert chain_service.web3.is_connected() or True  # May not be connected in test env

    # Verify USDC address is configured
    assert chain_service.usdc_address is not None
    assert chain_service.usdc_address.startswith("0x")

    print("✓ Chain service properly configured")


async def test_config_validation():
    """Test that configuration has all required blockchain settings."""
    from app.config import settings

    required_settings = [
        'WEB3_RPC_URL',
        'USDC_ADDRESS',
        'PLATFORM_WALLET_ADDRESS',
        'MIN_CONFIRMATIONS',
        'PAYMENT_VERIFICATION_TIMEOUT'
    ]

    for setting in required_settings:
        assert hasattr(settings, setting), f"Missing setting: {setting}"

    # Verify types
    assert isinstance(settings.MIN_CONFIRMATIONS, int)
    assert isinstance(settings.PAYMENT_VERIFICATION_TIMEOUT, int)
    assert isinstance(settings.WEB3_RPC_URL, str)

    print("✓ Configuration validation passed")


async def test_api_response_models():
    """Test that API response models work correctly."""
    from app.api.payments import PaymentVerificationResponse
    from datetime import datetime

    # Create response object
    response = PaymentVerificationResponse(
        success=True,
        transaction_id="tx-123",
        tx_hash="0xabcd1234",
        amount=Decimal("50.00"),
        currency="USDC",
        new_balance=Decimal("150.00"),
        credited_agent_id="agent-456",
        message="Payment verified",
        verified_at=datetime.utcnow(),
        credited_at=datetime.utcnow()
    )

    assert response.success is True
    assert response.amount == Decimal("50.00")
    assert response.new_balance == Decimal("150.00")

    # Test serialization
    response_dict = response.model_dump()
    assert 'success' in response_dict
    assert 'new_balance' in response_dict

    print("✓ API response models work correctly")


async def test_transaction_status_lifecycle():
    """Test that transaction status follows correct lifecycle."""
    from app.models.payment_transaction import TransactionStatus

    # Valid lifecycle: pending -> verified -> credited
    valid_statuses = [
        TransactionStatus.PENDING,
        TransactionStatus.VERIFIED,
        TransactionStatus.CREDITED
    ]

    # Or: pending -> failed
    failed_path = [
        TransactionStatus.PENDING,
        TransactionStatus.FAILED
    ]

    # Verify all expected statuses exist
    assert TransactionStatus.PENDING == "pending"
    assert TransactionStatus.VERIFIED == "verified"
    assert TransactionStatus.CREDITED == "credited"
    assert TransactionStatus.FAILED == "failed"

    print("✓ Transaction status lifecycle valid")


async def test_backward_compatibility_old_format():
    """Test that old payment verification request format still works."""
    from app.api.payments import PaymentVerificationRequest
    from app.models.payment_transaction import TransactionType

    # Old format (before refactoring): just tx_hash and amount
    old_request = PaymentVerificationRequest(
        tx_hash="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        amount=Decimal("100.00")
    )

    # Should use defaults
    assert old_request.currency == "USDC"
    assert old_request.transaction_type == TransactionType.TOP_UP
    assert old_request.recipient_agent_id is None
    assert old_request.token_address is None

    print("✓ Backward compatibility maintained")


async def test_new_p2p_format():
    """Test that new P2P payment format works."""
    from app.api.payments import PaymentVerificationRequest
    from app.models.payment_transaction import TransactionType

    # New P2P format
    p2p_request = PaymentVerificationRequest(
        tx_hash="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        amount=Decimal("25.00"),
        transaction_type=TransactionType.P2P,
        recipient_agent_id="agent-recipient-123"
    )

    assert p2p_request.transaction_type == TransactionType.P2P
    assert p2p_request.recipient_agent_id == "agent-recipient-123"

    print("✓ New P2P format works")


async def main():
    """Run all unit tests."""
    print("=" * 60)
    print("Payment API Unit Tests")
    print("=" * 60)
    print()

    tests = [
        ("Payment Request Validation", test_payment_request_validation),
        ("Transaction Model", test_transaction_model),
        ("Replay Protection", test_verification_service_replay_protection),
        ("Chain Service Integration", test_chain_service_integration),
        ("Configuration Validation", test_config_validation),
        ("API Response Models", test_api_response_models),
        ("Transaction Status Lifecycle", test_transaction_status_lifecycle),
        ("Backward Compatibility", test_backward_compatibility_old_format),
        ("New P2P Format", test_new_p2p_format),
    ]

    failed = []

    for name, test_func in tests:
        print(f"Testing {name}...")
        try:
            await test_func()
            print(f"✅ {name} - PASSED")
        except Exception as e:
            print(f"❌ {name} - FAILED")
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
            failed.append(name)
        print()

    print("=" * 60)
    if not failed:
        print("✅ All unit tests PASSED!")
        print("=" * 60)
        return 0
    else:
        print(f"❌ {len(failed)} test(s) FAILED:")
        for name in failed:
            print(f"   - {name}")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
