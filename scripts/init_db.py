#!/usr/bin/env python
"""
NeuroBridge 11D - Database Initialization Script
Creates all database tables and initial data
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models import Base, User, Simulation, EnergyData, SystemMetric
from backend.models.database import DatabaseManager
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_database(database_url: str = None):
    """Initialize database with all tables"""
    
    if not database_url:
        database_url = os.getenv("DATABASE_URL", "sqlite:///./neurobridge.db")
    
    logger.info(f"Initializing database with URL: {database_url}")
    
    db_manager = DatabaseManager(database_url)
    db_manager.init_db()
    
    logger.info("Database tables created successfully")
    
    # Create admin user if needed
    session = db_manager.get_session()
    try:
        admin = session.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@neurobridge.ng",
                hashed_password=User.hash_password("NeuroBridge2025!"),
                full_name="System Administrator",
                role="admin",
                is_active=True,
                is_verified=True
            )
            session.add(admin)
            session.commit()
            logger.info("Admin user created successfully")
        else:
            logger.info("Admin user already exists")
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
        session.rollback()
    finally:
        session.close()
    
    db_manager.close()
    logger.info("Database initialization complete")


if __name__ == "__main__":
    load_dotenv()
    init_database()