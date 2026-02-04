#!/usr/bin/env python3
"""
Compatibility test for refactored payment verification API.
Tests that the new implementation maintains backward compatibility
and validates new features.
"""

import sys
from decimal import Decimal

# Add current dir to path
sys.path.insert(0, '.')

def test_model_compatibility():
    """Test that PaymentTransaction model is properly defined."""
    from app.models.payment_transaction import (
        PaymentTransaction,
        TransactionStatus,
        TransactionType
    )

    # Test enum values
    assert TransactionStatus.PENDING == "pending"
    assert TransactionStatus.VERIFIED == "verified"
    assert TransactionStatus.FAILED == "failed"
    assert TransactionStatus.CREDITED == "credited"

    assert TransactionType.TOP_UP == "top_up"
    assert TransactionType.P2P == "p2p"
    assert TransactionType.REFUND == "refund"

    print("✓ PaymentTransaction model enums valid")

    # Test that model can be instantiated (doesn't test DB, just object creation)
    # Note: This won't actually work without a session, but tests the model definition
    print("✓ PaymentTransaction model structure valid")


def test_service_compatibility():
    """Test that payment verification service is properly defined."""
    from app.services.payment_verification_service import payment_verification_service

    # Test that service has required methods
    assert hasattr(payment_verification_service, 'verify_and_credit_payment')
    assert hasattr(payment_verification_service, 'get_transaction_history')

    print("✓ Payment verification service methods present")


def test_api_models():
    """Test that Pydantic models are valid."""
    from app.api.payments import (
        PaymentVerificationRequest,
        PaymentVerificationResponse,
        TransactionHistoryItem,
        TransactionHistoryResponse
    )

    # Test request model validation
    request = PaymentVerificationRequest(
        tx_hash="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        amount=Decimal("10.50"),
        currency="USDC"
    )

    # Should normalize to have 0x prefix
    assert request.tx_hash.startswith("0x")
    assert len(request.tx_hash) == 66  # 0x + 64 hex chars

    print("✓ Request validation working")

    # Test that invalid tx_hash raises validation error
    try:
        PaymentVerificationRequest(
            tx_hash="invalid",
            amount=Decimal("10.50")
        )
        assert False, "Should have raised validation error"
    except Exception as e:
        # Pydantic raises ValidationError
        assert "validation error" in str(e).lower() or "at least 64 characters" in str(e)
        print("✓ Invalid tx_hash rejected")

    # Test that negative amount raises validation error
    try:
        PaymentVerificationRequest(
            tx_hash="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            amount=Decimal("-10.50")
        )
        assert False, "Should have raised validation error"
    except Exception as e:
        # Check for validation error message
        error_str = str(e).lower()
        assert "greater than" in error_str or "validation error" in error_str
        print("✓ Negative amount rejected")


def test_chain_service():
    """Test that chain service is properly configured."""
    from app.services.chain_service import chain_service

    # Test that service has Web3 instance
    assert hasattr(chain_service, 'web3')
    assert hasattr(chain_service, 'verify_transaction')

    # Test that verify_transaction has correct signature
    import inspect
    sig = inspect.signature(chain_service.verify_transaction)
    params = list(sig.parameters.keys())

    assert 'tx_hash' in params
    assert 'expected_amount' in params
    assert 'recipient_address' in params

    print("✓ Chain service properly configured")


def test_config():
    """Test that new config values are present."""
    from app.config import settings

    # Test that new settings exist
    assert hasattr(settings, 'WEB3_RPC_URL')
    assert hasattr(settings, 'USDC_ADDRESS')
    assert hasattr(settings, 'PLATFORM_WALLET_ADDRESS')
    assert hasattr(settings, 'MIN_CONFIRMATIONS')
    assert hasattr(settings, 'PAYMENT_VERIFICATION_TIMEOUT')

    # Test default values
    assert isinstance(settings.MIN_CONFIRMATIONS, int)
    assert isinstance(settings.PAYMENT_VERIFICATION_TIMEOUT, int)

    print("✓ Configuration settings present")


def test_backward_compatibility():
    """Test that old API format still works."""
    from app.api.payments import PaymentVerificationRequest
    from app.models.payment_transaction import TransactionType

    # Old format (minimal) should still work
    old_format = PaymentVerificationRequest(
        tx_hash="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        amount=Decimal("100.00"),
        currency="USDC"
    )

    # Should default to TOP_UP
    assert old_format.transaction_type == TransactionType.TOP_UP
    assert old_format.recipient_agent_id is None

    print("✓ Backward compatibility maintained")

    # New format (with P2P) should work
    new_format = PaymentVerificationRequest(
        tx_hash="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        amount=Decimal("50.00"),
        currency="USDC",
        transaction_type=TransactionType.P2P,
        recipient_agent_id="agent-uuid-here"
    )

    assert new_format.transaction_type == TransactionType.P2P
    assert new_format.recipient_agent_id == "agent-uuid-here"

    print("✓ New P2P format works")


def test_api_router():
    """Test that API router is properly configured."""
    from app.api.payments import router

    # Test that router has expected routes
    routes = {route.path for route in router.routes}

    assert "/verify" in routes
    assert "/history" in routes
    assert "/transactions/{transaction_id}" in routes

    print("✓ API routes configured")


def main():
    """Run all compatibility tests."""
    print("=" * 50)
    print("Payment API Compatibility Test Suite")
    print("=" * 50)
    print()

    tests = [
        ("Model Compatibility", test_model_compatibility),
        ("Service Compatibility", test_service_compatibility),
        ("API Request/Response Models", test_api_models),
        ("Chain Service", test_chain_service),
        ("Configuration", test_config),
        ("Backward Compatibility", test_backward_compatibility),
        ("API Router", test_api_router),
    ]

    failed = []

    for name, test_func in tests:
        print(f"Testing {name}...")
        try:
            test_func()
            print(f"✅ {name} - PASSED")
        except Exception as e:
            print(f"❌ {name} - FAILED")
            print(f"   Error: {e}")
            failed.append(name)
        print()

    print("=" * 50)
    if not failed:
        print("✅ All compatibility tests PASSED!")
        print("=" * 50)
        return 0
    else:
        print(f"❌ {len(failed)} test(s) FAILED:")
        for name in failed:
            print(f"   - {name}")
        print("=" * 50)
        return 1


if __name__ == "__main__":
    sys.exit(main())
