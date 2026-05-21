
import os
import time
import threading
import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Generator, Optional, Any, Dict
from urllib.parse import quote_plus
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import QueuePool, NullPool
from sqlalchemy.exc import SQLAlchemyError, OperationalError

logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neurobridge:neurobridge@localhost:5432/neurobridge")
DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "10"))
DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))
DATABASE_POOL_TIMEOUT = int(os.getenv("DATABASE_POOL_TIMEOUT", "30"))
DATABASE_POOL_RECYCLE = int(os.getenv("DATABASE_POOL_RECYCLE", "3600"))
DATABASE_POOL_PRE_PING = os.getenv("DATABASE_POOL_PRE_PING", "true").lower() == "true"
DATABASE_ECHO = os.getenv("DATABASE_ECHO", "false").lower() == "true"
SQL_DEBUG = os.getenv("SQL_DEBUG", "false").lower() == "true"

# Connection retry settings
MAX_RETRIES = int(os.getenv("DB_MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("DB_RETRY_DELAY", "1.0"))
MAX_RETRY_BACKOFF = float(os.getenv("DB_MAX_RETRY_BACKOFF", "30.0"))

# Health check settings
HEALTH_CHECK_INTERVAL = int(os.getenv("DB_HEALTH_CHECK_INTERVAL", "60"))
HEALTH_CHECK_TIMEOUT = float(os.getenv("DB_HEALTH_CHECK_TIMEOUT", "5.0"))

# ============================================================================
# CONNECTION STRING BUILDING
# ============================================================================

def build_connection_string(url: str) -> str:
    """Build proper connection string with escaped credentials"""
    if "postgresql" in url or "postgres" in url:
        # Ensure PostgreSQL URL has proper parameters
        if "?" not in url:
            url += "?client_encoding=utf8"
        return url
    elif "mysql" in url:
        # MySQL specific parameters
        if "?" not in url:
            url += "?charset=utf8mb4"
        return url
    elif "sqlite" in url:
        # SQLite specific
        return url
    return url


def create_engine_with_retry(url: str, **kwargs) -> Any:
    """Create database engine with retry logic and exponential backoff"""
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            engine = create_engine(url, **kwargs)
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info(f"[Database] Engine created successfully (attempt {attempt + 1})")
            return engine
        except Exception as e:
            last_error = e
            backoff_time = min(RETRY_DELAY * (2 ** attempt), MAX_RETRY_BACKOFF)
            logger.warning(f"[Database] Connection attempt {attempt + 1} failed: {e} (retry in {backoff_time}s)")
            if attempt < MAX_RETRIES - 1:
                time.sleep(backoff_time)
    
    logger.error(f"[Database] Failed to create engine after {MAX_RETRIES} attempts: {last_error}")
    raise last_error


# ============================================================================
# DATABASE MANAGER (ENHANCED SINGLETON)
# ============================================================================

class DatabaseManager:
    """
    Enterprise-grade database manager with singleton pattern.
    
    Features:
    - Thread-safe singleton with double-checked locking
    - Automatic health monitoring and recovery
    - Connection pool management
    - Async support detection and management
    - Graceful shutdown
    """
    
    _instance: Optional['DatabaseManager'] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> 'DatabaseManager':
        """Thread-safe singleton - accepts NO parameters"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the database manager"""
        if self._initialized:
            return
        
        with self._lock:
            if self._initialized:
                return
            
            self._engine = None
            self._async_engine = None
            self._session_local = None
            self._async_session_local = None
            self._async_available = False
            self._health_status = "unknown"
            self._last_health_check = None
            
            # Statistics
            self._stats = {
                "singleton_created_at": datetime.now(timezone.utc).isoformat(),
                "initialization_count": 0,
                "last_initialization": None,
                "health_checks": 0,
                "health_check_failures": 0,
                "reconnections": 0,
                "last_health_check": None,
                "last_error": None
            }
            
            self._initialized = True
            self._stats["initialization_count"] += 1
            self._stats["last_initialization"] = datetime.now(timezone.utc).isoformat()
            
            logger.info("[DatabaseManager] Initialized")
    
    def is_initialized(self) -> bool:
        """Check if the manager is properly initialized"""
        return getattr(self, '_initialized', False)
    
    def reinitialize_if_needed(self) -> bool:
        """
        Reinitialize the manager if it's not properly initialized.
        Useful for recovery scenarios.
        
        Returns:
            True if reinitialization was performed
        """
        if not self.is_initialized():
            logger.warning("[DatabaseManager] Manager not initialized, reinitializing...")
            self.__init__()
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics"""
        return self._stats.copy()
    
    def initialize_engines(self) -> bool:
        """
        Initialize database engines.
        
        Returns:
            True if initialization successful
        """
        try:
            # Build connection string
            db_url = build_connection_string(DATABASE_URL)
            
            # Engine configuration
            engine_kwargs = {
                "poolclass": QueuePool,
                "pool_size": DATABASE_POOL_SIZE,
                "max_overflow": DATABASE_MAX_OVERFLOW,
                "pool_timeout": DATABASE_POOL_TIMEOUT,
                "pool_recycle": DATABASE_POOL_RECYCLE,
                "pool_pre_ping": DATABASE_POOL_PRE_PING,
                "echo": DATABASE_ECHO,
            }
            
            # SQLite special handling
            if "sqlite" in db_url:
                engine_kwargs = {
                    "poolclass": NullPool,
                    "connect_args": {"check_same_thread": False},
                    "echo": DATABASE_ECHO,
                }
            
            # Create engine
            self._engine = create_engine_with_retry(db_url, **engine_kwargs)
            
            # Create sync session factory
            self._session_local = sessionmaker(autocommit=False, autoflush=False, bind=self._engine)
            
            # Initialize async support
            self._init_async_support()
            
            # Setup event listeners
            self._setup_event_listeners()
            
            # Update health status
            self._health_status = "healthy"
            self._stats["reconnections"] += 1
            
            logger.info("[DatabaseManager] Engines initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"[DatabaseManager] Engine initialization failed: {e}")
            self._stats["last_error"] = str(e)
            self._health_status = "unhealthy"
            return False
    
    def _init_async_support(self):
        """Initialize async database support"""
        try:
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
            
            # Create async engine
            ASYNC_DATABASE_URL = os.getenv(
                "ASYNC_DATABASE_URL",
                DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
                if "postgresql" in DATABASE_URL
                else DATABASE_URL
            )
            
            self._async_engine = create_async_engine(
                ASYNC_DATABASE_URL,
                pool_size=DATABASE_POOL_SIZE,
                max_overflow=DATABASE_MAX_OVERFLOW,
                pool_timeout=DATABASE_POOL_TIMEOUT,
                pool_recycle=DATABASE_POOL_RECYCLE,
                pool_pre_ping=DATABASE_POOL_PRE_PING,
                echo=DATABASE_ECHO,
            )
            
            self._async_session_local = async_sessionmaker(
                self._async_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            self._async_available = True
            logger.info("[DatabaseManager] Async support enabled")
            
        except ImportError:
            self._async_available = False
            logger.info("[DatabaseManager] Async support not available (install sqlalchemy[asyncio])")
        except Exception as e:
            self._async_available = False
            logger.warning(f"[DatabaseManager] Async initialization failed: {e}")
    
    def _setup_event_listeners(self):
        """Setup SQLAlchemy event listeners"""
        if not self._engine:
            return
        
        @event.listens_for(self._engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            """Log SQL statements in debug mode"""
            if SQL_DEBUG:
                logger.debug(f"[SQL] {statement[:500]}")
                if parameters:
                    logger.debug(f"[SQL] Params: {str(parameters)[:200]}")
            
            # Store start time for slow query detection
            context._query_start_time = time.time()
        
        @event.listens_for(self._engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            """Log slow queries"""
            if hasattr(context, '_query_start_time'):
                total = time.time() - context._query_start_time
                if total > 1.0:
                    logger.warning(f"[Database] Slow query ({total:.3f}s): {statement[:200]}")
        
        @event.listens_for(self._engine, "connect")
        def receive_connect(dbapi_connection, connection_record):
            """Called when a new database connection is created"""
            logger.debug("[Database] New connection established")
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check.
        
        Returns:
            Health status dictionary
        """
        self._stats["health_checks"] += 1
        self._stats["last_health_check"] = datetime.now(timezone.utc).isoformat()
        
        result = {
            "healthy": False,
            "sync_available": False,
            "async_available": self._async_available,
            "engine_initialized": self._engine is not None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Check sync connection
        if self._engine:
            try:
                with self._engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                result["sync_available"] = True
            except Exception as e:
                logger.warning(f"[DatabaseManager] Sync health check failed: {e}")
                self._stats["health_check_failures"] += 1
                result["sync_error"] = str(e)
        
        # Check async connection
        if self._async_available and self._async_engine:
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def check():
                    async with self._async_engine.connect() as conn:
                        await conn.execute(text("SELECT 1"))
                
                loop.run_until_complete(check())
                loop.close()
                result["async_available"] = True
            except Exception as e:
                logger.warning(f"[DatabaseManager] Async health check failed: {e}")
                result["async_error"] = str(e)
        
        result["healthy"] = result["sync_available"]
        self._health_status = "healthy" if result["healthy"] else "unhealthy"
        
        return result
    
    @property
    def engine(self):
        """Get sync engine"""
        if not self._engine:
            self.initialize_engines()
        return self._engine
    
    @property
    def async_engine(self):
        """Get async engine"""
        if not self._async_engine and self._async_available:
            self.initialize_engines()
        return self._async_engine
    
    @property
    def SessionLocal(self):
        """Get sync session factory"""
        if not self._session_local:
            self.initialize_engines()
        return self._session_local
    
    @property
    def AsyncSessionLocal(self):
        """Get async session factory"""
        if not self._async_session_local and self._async_available:
            self.initialize_engines()
        return self._async_session_local
    
    @property
    def async_available(self) -> bool:
        """Check if async is available"""
        return self._async_available
    
    def get_pool_status(self) -> Dict[str, Any]:
        """Get connection pool status"""
        if not self._engine:
            return {"error": "Engine not initialized"}
        
        pool = self._engine.pool
        return {
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "overflow": pool.overflow(),
            "total": pool.total(),
            "max_overflow": DATABASE_MAX_OVERFLOW,
            "pool_size": DATABASE_POOL_SIZE,
            "timeout": DATABASE_POOL_TIMEOUT,
            "recycle": DATABASE_POOL_RECYCLE
        }
    
    def shutdown(self) -> None:
        """Gracefully shutdown database connections"""
        logger.info("[DatabaseManager] Shutting down...")
        
        if self._engine:
            self._engine.dispose()
            logger.info("[DatabaseManager] Sync engine disposed")
        
        if self._async_engine:
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._async_engine.dispose())
                loop.close()
                logger.info("[DatabaseManager] Async engine disposed")
            except Exception as e:
                logger.warning(f"[DatabaseManager] Async dispose error: {e}")
        
        self._initialized = False
        logger.info("[DatabaseManager] Shutdown complete")


# ============================================================================
# GLOBAL DATABASE MANAGER INSTANCE
# ============================================================================

_db_manager: Optional[DatabaseManager] = None
_db_manager_lock = threading.RLock()


def get_db_manager() -> DatabaseManager:
    """Get global database manager instance"""
    global _db_manager
    
    if _db_manager is None:
        with _db_manager_lock:
            if _db_manager is None:
                _db_manager = DatabaseManager()
                _db_manager.initialize_engines()
                logger.info(f"[DatabaseManager] Global instance created | ID: {id(_db_manager)}")
    
    return _db_manager


def get_db_manager_safe() -> Optional[DatabaseManager]:
    """
    Safely get database manager without auto-creating.
    Returns None if not initialized.
    """
    global _db_manager
    return _db_manager


def reset_db_manager():
    """
    Reset database manager singleton (for testing/hot-reload).
    
    WARNING: This should only be used in testing or during hot-reload.
    """
    global _db_manager
    with _db_manager_lock:
        if _db_manager is not None:
            _db_manager.shutdown()
            logger.info("[DatabaseManager] Resetting singleton instance")
            _db_manager = None
            logger.info("[DatabaseManager] Manager singleton reset")


def is_db_manager_initialized() -> bool:
    """Check if database manager is initialized"""
    global _db_manager
    return _db_manager is not None and _db_manager.is_initialized()


# ============================================================================
# BACKWARD COMPATIBILITY WRAPPERS
# ============================================================================

def get_engine():
    """Get sync engine (backward compatibility)"""
    return get_db_manager().engine


def get_async_engine():
    """Get async engine (backward compatibility)"""
    return get_db_manager().async_engine


def get_session_local():
    """Get sync session factory (backward compatibility)"""
    return get_db_manager().SessionLocal


def get_async_session_local():
    """Get async session factory (backward compatibility)"""
    return get_db_manager().AsyncSessionLocal


def is_async_available() -> bool:
    """Check if async is available (backward compatibility)"""
    return get_db_manager().async_available


# ============================================================================
# INITIALIZE LEGACY GLOBALS (Backward Compatibility)
# ============================================================================

# Initialize manager
_manager = get_db_manager()

# Set legacy globals for backward compatibility
engine = _manager.engine
async_engine = _manager.async_engine
SessionLocal = _manager.SessionLocal
AsyncSessionLocal = _manager.AsyncSessionLocal
ASYNC_AVAILABLE = _manager.async_available

# ============================================================================
# BASE MODEL CLASS
# ============================================================================

class ModelMixin:
    """Common model mixin with utility methods"""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary"""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }
    
    def update(self, data: Dict[str, Any]) -> None:
        """Update model instance from dictionary"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)


Base = declarative_base(cls=ModelMixin)


# ============================================================================
# SESSION CONTEXT MANAGERS
# ============================================================================

@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Database session context manager (sync)
    
    Usage:
        with get_db() as db:
            db.query(User).all()
    """
    session_local = get_session_local()
    db = session_local()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[Database] Transaction error: {e}")
        raise
    finally:
        db.close()


@asynccontextmanager
async def get_async_db() -> Generator[Any, None, None]:
    """
    Async database session context manager
    
    Usage:
        async with get_async_db() as db:
            result = await db.execute(select(User))
    """
    if not is_async_available():
        raise RuntimeError("Async database not available")
    
    async_session_local = get_async_session_local()
    async with async_session_local() as db:
        try:
            yield db
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"[Database] Async transaction error: {e}")
            raise
        finally:
            await db.close()


def get_db_session() -> Session:
    """Get a new database session"""
    session_local = get_session_local()
    return session_local()


def get_scoped_session() -> Session:
    """Get scoped session (thread-safe)"""
    session_local = get_session_local()
    return scoped_session(session_local)


# ============================================================================
# HEALTH CHECK (Backward Compatibility)
# ============================================================================

def check_db_connection() -> bool:
    """Check database connectivity"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"[Database] Connection check failed: {e}")
        return False


async def check_async_db_connection() -> bool:
    """Check async database connectivity"""
    if not ASYNC_AVAILABLE:
        return False
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"[Database] Async connection check failed: {e}")
        return False


def get_db_status() -> Dict[str, Any]:
    """Get detailed database status"""
    manager = get_db_manager()
    health = manager.health_check()
    pool_status = manager.get_pool_status()
    
    return {
        "connected": health["sync_available"],
        "url": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL.split("://")[0],
        "async_available": ASYNC_AVAILABLE,
        "pool_size": DATABASE_POOL_SIZE,
        "max_overflow": DATABASE_MAX_OVERFLOW,
        "pool_timeout": DATABASE_POOL_TIMEOUT,
        "health_status": health,
        "pool_status": pool_status,
        "manager_stats": manager.get_stats(),
        "singleton_initialized": is_db_manager_initialized()
    }


# ============================================================================
# INITIALIZATION AND MIGRATION
# ============================================================================

def init_db():
    """Initialize database - create all tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("[Database] Tables created/verified successfully")
    except Exception as e:
        logger.error(f"[Database] Table creation failed: {e}")
        raise


def drop_db():
    """Drop all tables (development only)"""
    env = os.getenv("ENVIRONMENT", "development")
    if env in ["development", "testing"]:
        Base.metadata.drop_all(bind=engine)
        logger.warning("[Database] All tables dropped!")
    else:
        logger.error("[Database] Cannot drop tables in production!")


async def init_async_db():
    """Initialize async database"""
    if not ASYNC_AVAILABLE:
        return
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("[Database] Async tables created/verified")
    except Exception as e:
        logger.error(f"[Database] Async table creation failed: {e}")
        raise


# ============================================================================
# GRACEFUL SHUTDOWN
# ============================================================================

async def shutdown_database():
    """Gracefully shutdown database connections"""
    logger.info("[Database] Shutting down...")
    manager = get_db_manager_safe()
    if manager:
        manager.shutdown()
    logger.info("[Database] Shutdown complete")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Core
    "Base",
    "engine",
    "SessionLocal",
    "get_scoped_session",
    
    # Context managers
    "get_db",
    "get_db_session",
    
    # Async (if available)
    "get_async_db",
    "AsyncSessionLocal",
    "async_engine",
    "ASYNC_AVAILABLE",
    
    # Utilities
    "init_db",
    "drop_db",
    "init_async_db",
    "check_db_connection",
    "check_async_db_connection",
    "get_db_status",
    "shutdown_database",
    
    # Mixin
    "ModelMixin",
    
    # Manager (new)
    "DatabaseManager",
    "get_db_manager",
    "get_db_manager_safe",
    "reset_db_manager",
    "is_db_manager_initialized",
]

# ============================================================================
# INITIALIZATION LOG
# ============================================================================

logger.info("=" * 60)
logger.info("[Database] Configuration loaded")
logger.info(f"[Database] URL: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL.split('://')[0]}")
logger.info(f"[Database] Pool Size: {DATABASE_POOL_SIZE}")
logger.info(f"[Database] Max Overflow: {DATABASE_MAX_OVERFLOW}")
logger.info(f"[Database] Async Available: {ASYNC_AVAILABLE}")
logger.info(f"[Database] Manager Initialized: {is_db_manager_initialized()}")
logger.info("=" * 60)

# Test connection on startup
if not check_db_connection():
    logger.warning("[Database] Initial connection check failed - will retry on demand")
else:
    logger.info("[Database] Initial connection successful")
