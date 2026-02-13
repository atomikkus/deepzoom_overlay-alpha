#!/usr/bin/env python3
"""
Test authentication setup for WSI Viewer.
Run after installing dependencies: pip install -r requirements.txt
"""

import os
import sys

def test_imports():
    """Test that required modules are installed."""
    print("Testing imports...")
    try:
        import bcrypt
        import hashlib
        from fastapi.security import HTTPBasic, HTTPBasicCredentials
        print("✓ All required modules available")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        print("Run: pip install -r requirements.txt")
        return False

def test_password_hashing():
    """Test password hashing and verification (same scheme as app: SHA256 then bcrypt)."""
    import hashlib
    import bcrypt
    
    def _to_bcrypt_input(password):
        return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")
    
    print("\nTesting password hashing...")
    test_password = "test_password_123"
    password_hash = bcrypt.hashpw(_to_bcrypt_input(test_password), bcrypt.gensalt()).decode("ascii")
    
    print(f"  Password: {test_password}")
    print(f"  Hash: {password_hash[:50]}...")
    
    # Test verification
    if bcrypt.checkpw(_to_bcrypt_input(test_password), password_hash.encode("ascii")):
        print("  ✓ Password verification successful")
    else:
        print("  ✗ Password verification failed")
        return False
    
    # Test wrong password
    if not bcrypt.checkpw(_to_bcrypt_input("wrong_password"), password_hash.encode("ascii")):
        print("  ✓ Wrong password correctly rejected")
    else:
        print("  ✗ Wrong password incorrectly accepted")
        return False
    
    # Test long password (regression test for 72-byte limit)
    long_password = "x" * 200
    long_hash = bcrypt.hashpw(_to_bcrypt_input(long_password), bcrypt.gensalt()).decode("ascii")
    if bcrypt.checkpw(_to_bcrypt_input(long_password), long_hash.encode("ascii")):
        print("  ✓ Long password (200 chars) works")
    else:
        print("  ✗ Long password verification failed")
        return False
    
    return True

def test_environment_config():
    """Test environment variable configuration."""
    print("\nTesting environment configuration...")
    
    # Set test environment
    os.environ["AUTH_USERNAME"] = "testuser"
    os.environ["AUTH_PASSWORD"] = "testpass"
    os.environ["AUTH_ENABLED"] = "true"
    
    print(f"  AUTH_USERNAME: {os.getenv('AUTH_USERNAME')}")
    print(f"  AUTH_PASSWORD: {'*' * len(os.getenv('AUTH_PASSWORD', ''))}")
    print(f"  AUTH_ENABLED: {os.getenv('AUTH_ENABLED')}")
    print("  ✓ Environment variables configured")
    
    return True

def main():
    print("=" * 60)
    print("WSI Viewer - Authentication Test")
    print("=" * 60)
    
    tests = [
        ("Import Test", test_imports),
        ("Password Hashing Test", test_password_hashing),
        ("Environment Config Test", test_environment_config),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            if callable(test_func):
                result = test_func()
                results.append((name, result))
        except Exception as e:
            print(f"✗ {name} failed with error: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("Test Results:")
    print("=" * 60)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(result for _, result in results)
    
    print("=" * 60)
    if all_passed:
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
