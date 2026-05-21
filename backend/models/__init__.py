"""
NeuroBridge 11D - Database Models
Enterprise-grade SQLAlchemy models for energy intelligence
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, Text, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone, timedelta
import uuid
from typing import Optional, Dict, Any, List
from passlib.context import CryptContext

Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(Base):
    """User model for authentication and authorization"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(200), nullable=False)
    full_name = Column(String(100))
    role = Column(String(20), default="user")  # admin, user, viewer
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    simulations = relationship("Simulation", back_populates="user", cascade="all, delete-orphan")
    energy_data = relationship("EnergyData", back_populates="user", cascade="all, delete-orphan")
    
    def verify_password(self, password: str) -> bool:
        """Verify user password"""
        return pwd_context.verify(password, self.hashed_password)
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password for storage"""
        return pwd_context.hash(password)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary"""
        return {
            "id": self.id,
            "uuid": str(self.uuid),
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class Simulation(Base):
    """Energy simulation model"""
    __tablename__ = "simulations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    simulation_id = Column(String(50), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sector = Column(String(30), nullable=False, index=True)  # renewables, oil_gas, etc.
    context = Column(String(200))
    input_energy = Column(Float, nullable=False)
    entropy_loss = Column(Float, default=0.05)
    yield_value = Column(Float, nullable=False)
    stability_score = Column(Float, nullable=False)
    quantum_coherence = Column(Float)
    manifold_integrity = Column(Float)
    data_source = Column(String(50))  # REAL_TIME, SIMULATED, HYBRID
    kernel_mode = Column(String(20))  # NATIVE_C++, SIMULATED
    execution_time_ms = Column(Float)
    metadata_json = Column(JSON, default={})
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="simulations")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert simulation to dictionary"""
        return {
            "id": self.id,
            "simulation_id": self.simulation_id,
            "user_id": self.user_id,
            "sector": self.sector,
            "context": self.context,
            "input_energy": self.input_energy,
            "entropy_loss": self.entropy_loss,
            "yield_value": self.yield_value,
            "stability_score": self.stability_score,
            "quantum_coherence": self.quantum_coherence,
            "manifold_integrity": self.manifold_integrity,
            "data_source": self.data_source,
            "kernel_mode": self.kernel_mode,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata_json,
            "created_at": self.created_at.isoformat()
        }


class EnergyData(Base):
    """Real-time energy data model"""
    __tablename__ = "energy_data"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    data_id = Column(String(50), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    source = Column(String(30))  # HARDWARE, NASA, GEE, HYBRID
    
    # Energy metrics
    grid_load_mw = Column(Float)
    grid_frequency_hz = Column(Float)
    renewable_percentage = Column(Float)
    
    # Environmental data
    temperature_c = Column(Float)
    humidity_percent = Column(Float)
    solar_ghi_wm2 = Column(Float)
    wind_speed_ms = Column(Float)
    cloud_cover_percent = Column(Float)
    
    # Vegetation/Geospatial
    vegetation_health = Column(Float)
    thermal_anomaly = Column(Float)
    
    # Quantum metrics
    quantum_coherence = Column(Float)
    lattice_integrity = Column(Float)
    
    # Metadata
    data_quality = Column(Float)
    metadata_json = Column(JSON, default={})
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="energy_data")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert energy data to dictionary"""
        return {
            "id": self.id,
            "data_id": self.data_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "grid_load_mw": self.grid_load_mw,
            "grid_frequency_hz": self.grid_frequency_hz,
            "renewable_percentage": self.renewable_percentage,
            "temperature_c": self.temperature_c,
            "humidity_percent": self.humidity_percent,
            "solar_ghi_wm2": self.solar_ghi_wm2,
            "wind_speed_ms": self.wind_speed_ms,
            "cloud_cover_percent": self.cloud_cover_percent,
            "vegetation_health": self.vegetation_health,
            "thermal_anomaly": self.thermal_anomaly,
            "quantum_coherence": self.quantum_coherence,
            "lattice_integrity": self.lattice_integrity,
            "data_quality": self.data_quality
        }


class SystemMetric(Base):
    """System performance metrics model"""
    __tablename__ = "system_metrics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    metric_name = Column(String(50), nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    unit = Column(String(20))
    tags = Column(JSON, default={})
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metric to dictionary"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "unit": self.unit,
            "tags": self.tags
        }


# Database initialization
class DatabaseManager:
    """Database connection manager"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        self.SessionLocal = None
    
    def init_db(self):
        """Initialize database connection"""
        self.engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self) -> Session:
        """Get database session"""
        if not self.SessionLocal:
            self.init_db()
        return self.SessionLocal()
    
    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()