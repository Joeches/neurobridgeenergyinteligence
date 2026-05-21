#!/usr/bin/env python
"""
NeuroBridge 11D - Create Admin User Script
"""

import sys
import os
import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models import User
from backend.models.database import DatabaseManager
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_admin_user():
    """Create admin user interactively"""
    
    print("\n" + "="*60)
    print("NeuroBridge 11D - Admin User Creation")
    print("="*60)
    
    username = input("Username (admin): ").strip() or "admin"
    email = input("Email (admin@neurobridge.ng): ").strip() or "admin@neurobridge.ng"
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm Password: ")
    
    if password != confirm:
        print("Error: Passwords do not match")
        return
    
    database_url = os.getenv("DATABASE_URL", "sqlite:///./neurobridge.db")
    db_manager = DatabaseManager(database_url)
    db_manager.init_db()
    
    session = db_manager.get_session()
    try:
        existing = session.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing:
            print(f"Error: User {username} or {email} already exists")
            return
        
        user = User(
            username=username,
            email=email,
            hashed_password=User.hash_password(password),
            full_name="Administrator",
            role="admin",
            is_active=True,
            is_verified=True
        )
        
        session.add(user)
        session.commit()
        
        print(f"\n✅ Admin user '{username}' created successfully!")
        
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
        session.rollback()
    finally:
        session.close()
        db_manager.close()


if __name__ == "__main__":
    load_dotenv()
    create_admin_user()