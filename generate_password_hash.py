#!/usr/bin/env python3
"""
Generate password hash for WSI Viewer authentication.
Usage: python generate_password_hash.py

Hashes with SHA256 then bcrypt so passwords of any length work (bcrypt has 72-byte limit).
Must match the scheme in app.py (uses bcrypt library directly).
"""

import hashlib
import sys

try:
    import bcrypt
except ImportError:
    print("Error: bcrypt is not installed. Run: pip install passlib[bcrypt]")
    sys.exit(1)


def _to_bcrypt_input(password: str) -> bytes:
    """Same as app.py: SHA256 hex digest as bytes (64 bytes) so bcrypt never sees > 72 bytes."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def main():
    print("WSI Viewer - Password Hash Generator")
    print("=" * 50)
    
    password = input("Enter password: ")
    if not password:
        print("Error: Password cannot be empty")
        sys.exit(1)
    
    confirm = input("Confirm password: ")
    if password != confirm:
        print("Error: Passwords do not match")
        sys.exit(1)
    
    # Hash with same scheme as app.py: SHA256(password) then bcrypt
    try:
        password_hash = bcrypt.hashpw(_to_bcrypt_input(password), bcrypt.gensalt()).decode("ascii")
    except Exception as e:
        print(f"Error generating hash: {e}")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    print("Password hash generated successfully!")
    print("=" * 50)
    print("\nAdd this to your .env file:")
    print(f"AUTH_PASSWORD_HASH={password_hash}")
    print("\nOr set as environment variable:")
    print(f"export AUTH_PASSWORD_HASH='{password_hash}'")
    print("\n" + "=" * 50)

if __name__ == "__main__":
    main()
