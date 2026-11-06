#!/usr/bin/env python3
"""
TPMS Admin authentication and authorization utilities.
"""

import hashlib
import json
import os

ADMIN_USERS_FILE = '.tpms_admin_users.json'

def hash_password(password):
    """Hash a password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

def init_admin_users(username, password):
    """Initialize admin users file with a user. Creates or overwrites the file."""
    admin_users = {
        username: hash_password(password)
    }
    with open(ADMIN_USERS_FILE, 'w') as f:
        json.dump(admin_users, f, indent=2)
    os.chmod(ADMIN_USERS_FILE, 0o600)  # Read/write for owner only
    print(f"✓ Admin user '{username}' created in {ADMIN_USERS_FILE}")

def add_admin_user(username, password):
    """Add a new admin user to the file."""
    admin_users = load_admin_users()
    if username in admin_users:
        print(f"✗ User '{username}' already exists")
        return False
    admin_users[username] = hash_password(password)
    with open(ADMIN_USERS_FILE, 'w') as f:
        json.dump(admin_users, f, indent=2)
    os.chmod(ADMIN_USERS_FILE, 0o600)
    print(f"✓ Admin user '{username}' added")
    return True

def load_admin_users():
    """Load admin users from file. Returns empty dict if file doesn't exist."""
    if not os.path.exists(ADMIN_USERS_FILE):
        return {}
    try:
        with open(ADMIN_USERS_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def verify_credentials(username, password):
    """Verify username and password. Returns True if valid."""
    admin_users = load_admin_users()
    if username not in admin_users:
        return False
    expected_hash = admin_users[username]
    provided_hash = hash_password(password)
    return expected_hash == provided_hash

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print("Usage: python3 tpms_admin.py <init|add> <username> <password>")
        sys.exit(1)

    cmd = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]

    if cmd == 'init':
        init_admin_users(username, password)
    elif cmd == 'add':
        add_admin_user(username, password)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
