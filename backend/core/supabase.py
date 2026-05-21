
import os
import asyncio
import logging
import json
from typing import Dict, Any, Optional, List, Union, Callable
from datetime import datetime, timezone, timedelta
from functools import wraps
from contextlib import asynccontextmanager

from supabase import create_client, Client
from postgrest.exceptions import APIError
from realtime.connection import Socket

# Optional: for async operations
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "neurobridge-reports")
SUPABASE_TIMEOUT = int(os.getenv("SUPABASE_TIMEOUT", "30"))
SUPABASE_MAX_RETRIES = int(os.getenv("SUPABASE_MAX_RETRIES", "3"))
SUPABASE_RETRY_DELAY = float(os.getenv("SUPABASE_RETRY_DELAY", "1.0"))


# ============================================================================
# TABLE NAMES
# ============================================================================

class Tables:
    """Database table names"""
    SIMULATIONS = "simulations"
    ENERGY_DATA = "energy_data"
    ADFI_INJECTIONS = "adfi_injections"
    SYSTEM_METRICS = "system_metrics"
    AECE_DECISIONS = "aece_decisions"
    AECE_STATE = "aece_state"
    PARTNERS = "partners"
    API_KEYS = "api_keys"
    AUDIT_LOGS = "audit_logs"
    WEATHER_DATA = "weather_data"
    PREDICTIONS = "predictions"


# ============================================================================
# RETRY DECORATOR
# ============================================================================

def retry_on_failure(max_retries: int = SUPABASE_MAX_RETRIES, delay: float = SUPABASE_RETRY_DELAY):
    """Decorator to retry database operations on failure"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay * (attempt + 1))
                        logger.warning(f"[Database] Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}")
                    else:
                        logger.error(f"[Database] Failed {func.__name__} after {max_retries} attempts: {e}")
            raise last_error
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(delay * (attempt + 1))
                        logger.warning(f"[Database] Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}")
                    else:
                        logger.error(f"[Database] Failed {func.__name__} after {max_retries} attempts: {e}")
            raise last_error
        
        # Determine if async or sync
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# ============================================================================
# SUPABASE CLIENT
# ============================================================================

class SupabaseClient:
    """
    Enterprise Supabase client for production use with async support.
    """
    
    def __init__(self):
        self._client = None
        self._async_client = None
        self._available = False
        self._last_health_check = 0
        self._realtime_subscriptions = {}
        self._init_client()
    
    def _init_client(self):
        """Initialize Supabase client"""
        if not SUPABASE_URL or not SUPABASE_KEY:
            logger.warning("[Database] Supabase credentials not configured")
            self._available = False
            return
        
        try:
            self._client = create_client(SUPABASE_URL, SUPABASE_KEY)
            self._available = True
            logger.info(f"[Database] Supabase connected: {SUPABASE_URL}")
            
            # Test connection
            self._client.table(Tables.SIMULATIONS).select("count").limit(1).execute()
            logger.info("[Database] Connection test successful")
        except Exception as e:
            logger.error(f"[Database] Supabase connection failed: {e}")
            self._client = None
            self._available = False
    
    def _check_health(self):
        """Check database health"""
        if not self._available:
            self._init_client()
    
    @property
    def available(self) -> bool:
        """Check if database is available"""
        if not self._available:
            self._check_health()
        return self._available and self._client is not None
    
    @property
    def client(self) -> Optional[Client]:
        """Get Supabase client"""
        if not self.available:
            return None
        return self._client
    
    # ============================================================================
    # HELPER METHODS
    # ============================================================================
    
    def _prepare_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare record for insertion (add timestamps)"""
        record_copy = record.copy()
        if "created_at" not in record_copy:
            record_copy["created_at"] = datetime.now(timezone.utc).isoformat()
        if "updated_at" not in record_copy:
            record_copy["updated_at"] = datetime.now(timezone.utc).isoformat()
        return record_copy
    
    # ============================================================================
    # SIMULATION RECORDS
    # ============================================================================
    
    @retry_on_failure()
    def save_simulation(self, simulation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save simulation result to database"""
        if not self.available:
            return {"error": "Database not available", "saved": False}
        
        try:
            record = self._prepare_record(simulation_data)
            result = self._client.table(Tables.SIMULATIONS).insert(record).execute()
            logger.info(f"[Database] Simulation saved: {simulation_data.get('simulation_id')}")
            return {"saved": True, "data": result.data[0] if result.data else None}
        except APIError as e:
            logger.error(f"[Database] Failed to save simulation: {e}")
            return {"error": str(e), "saved": False}
        except Exception as e:
            logger.error(f"[Database] Unexpected error: {e}")
            return {"error": str(e), "saved": False}
    
    @retry_on_failure()
    def save_simulation_batch(self, simulations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Save multiple simulations in batch"""
        if not self.available:
            return {"error": "Database not available", "saved": 0}
        
        try:
            records = [self._prepare_record(s) for s in simulations]
            result = self._client.table(Tables.SIMULATIONS).insert(records).execute()
            logger.info(f"[Database] Batch saved: {len(records)} simulations")
            return {"saved": len(result.data) if result.data else 0, "data": result.data}
        except Exception as e:
            logger.error(f"[Database] Batch save failed: {e}")
            return {"error": str(e), "saved": 0}
    
    @retry_on_failure()
    def get_simulations(self, limit: int = 100, offset: int = 0, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Get recent simulations with optional filters"""
        if not self.available:
            return []
        
        try:
            query = self._client.table(Tables.SIMULATIONS).select("*")
            
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)
            
            result = query.order("created_at", desc=True).limit(limit).offset(offset).execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[Database] Failed to get simulations: {e}")
            return []
    
    @retry_on_failure()
    def get_simulation_by_id(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        """Get simulation by ID"""
        if not self.available:
            return None
        
        try:
            result = self._client.table(Tables.SIMULATIONS).select("*").eq("simulation_id", simulation_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"[Database] Failed to get simulation: {e}")
            return None
    
    @retry_on_failure()
    def update_simulation(self, simulation_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update simulation record"""
        if not self.available:
            return None
        
        try:
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            result = self._client.table(Tables.SIMULATIONS).update(updates).eq("simulation_id", simulation_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"[Database] Failed to update simulation: {e}")
            return None
    
    # ============================================================================
    # ENERGY DATA
    # ============================================================================
    
    @retry_on_failure()
    def save_energy_data(self, energy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save energy telemetry data"""
        if not self.available:
            return {"error": "Database not available", "saved": False}
        
        try:
            record = self._prepare_record(energy_data)
            result = self._client.table(Tables.ENERGY_DATA).insert(record).execute()
            logger.debug(f"[Database] Energy data saved")
            return {"saved": True, "data": result.data[0] if result.data else None}
        except Exception as e:
            logger.error(f"[Database] Failed to save energy data: {e}")
            return {"error": str(e), "saved": False}
    
    @retry_on_failure()
    def save_energy_data_batch(self, energy_data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Save multiple energy data points in batch"""
        if not self.available:
            return {"error": "Database not available", "saved": 0}
        
        try:
            records = [self._prepare_record(d) for d in energy_data_list]
            result = self._client.table(Tables.ENERGY_DATA).insert(records).execute()
            logger.info(f"[Database] Batch saved: {len(records)} energy records")
            return {"saved": len(result.data) if result.data else 0, "data": result.data}
        except Exception as e:
            logger.error(f"[Database] Batch save failed: {e}")
            return {"error": str(e), "saved": 0}
    
    @retry_on_failure()
    def get_energy_data(self, hours: int = 24, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get recent energy data"""
        if not self.available:
            return []
        
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            result = self._client.table(Tables.ENERGY_DATA)\
                .select("*")\
                .gte("created_at", cutoff)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[Database] Failed to get energy data: {e}")
            return []
    
    @retry_on_failure()
    def get_energy_aggregates(self, hours: int = 24) -> Dict[str, Any]:
        """Get aggregated energy statistics"""
        if not self.available:
            return {}
        
        try:
            data = self.get_energy_data(hours)
            if not data:
                return {}
            
            total_energy = sum(d.get("power_kw", 0) for d in data)
            avg_power = total_energy / len(data) if data else 0
            max_power = max(d.get("power_kw", 0) for d in data) if data else 0
            min_power = min(d.get("power_kw", 0) for d in data) if data else 0
            
            return {
                "total_energy_kwh": round(total_energy, 2),
                "average_power_kw": round(avg_power, 2),
                "max_power_kw": round(max_power, 2),
                "min_power_kw": round(min_power, 2),
                "data_points": len(data),
                "period_hours": hours,
            }
        except Exception as e:
            logger.error(f"[Database] Failed to get energy aggregates: {e}")
            return {}
    
    # ============================================================================
    # ADFI INJECTIONS
    # ============================================================================
    
    @retry_on_failure()
    def save_adfi_injection(self, injection_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save ADFI injection record"""
        if not self.available:
            return {"error": "Database not available", "saved": False}
        
        try:
            record = self._prepare_record(injection_data)
            result = self._client.table(Tables.ADFI_INJECTIONS).insert(record).execute()
            logger.info(f"[Database] ADFI injection saved")
            return {"saved": True, "data": result.data[0] if result.data else None}
        except Exception as e:
            logger.error(f"[Database] Failed to save ADFI injection: {e}")
            return {"error": str(e), "saved": False}
    
    @retry_on_failure()
    def get_adfi_injections(self, limit: int = 100, sector: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent ADFI injections with optional sector filter"""
        if not self.available:
            return []
        
        try:
            query = self._client.table(Tables.ADFI_INJECTIONS).select("*")
            
            if sector:
                query = query.eq("sector", sector)
            
            result = query.order("created_at", desc=True).limit(limit).execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[Database] Failed to get ADFI injections: {e}")
            return []
    
    @retry_on_failure()
    def get_adfi_statistics(self) -> Dict[str, Any]:
        """Get ADFI injection statistics"""
        if not self.available:
            return {}
        
        try:
            # Get total injections by sector
            result = self._client.table(Tables.ADFI_INJECTIONS).select("sector").execute()
            data = result.data if result.data else []
            
            sector_counts = {}
            for item in data:
                sector = item.get("sector", "unknown")
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
            
            return {
                "total_injections": len(data),
                "by_sector": sector_counts,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"[Database] Failed to get ADFI statistics: {e}")
            return {}
    
    # ============================================================================
    # SYSTEM METRICS
    # ============================================================================
    
    @retry_on_failure()
    def save_system_metrics(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Save system metrics"""
        if not self.available:
            return {"error": "Database not available", "saved": False}
        
        try:
            record = self._prepare_record(metrics)
            result = self._client.table(Tables.SYSTEM_METRICS).insert(record).execute()
            return {"saved": True, "data": result.data[0] if result.data else None}
        except Exception as e:
            logger.error(f"[Database] Failed to save system metrics: {e}")
            return {"error": str(e), "saved": False}
    
    @retry_on_failure()
    def get_system_metrics(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent system metrics"""
        if not self.available:
            return []
        
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            result = self._client.table(Tables.SYSTEM_METRICS)\
                .select("*")\
                .gte("created_at", cutoff)\
                .order("created_at", desc=True)\
                .execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[Database] Failed to get system metrics: {e}")
            return []
    
    # ============================================================================
    # AECE STATE
    # ============================================================================
    
    @retry_on_failure()
    def save_aece_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Save AECE decision record"""
        if not self.available:
            return {"error": "Database not available", "saved": False}
        
        try:
            record = self._prepare_record(decision)
            result = self._client.table(Tables.AECE_DECISIONS).insert(record).execute()
            logger.info(f"[Database] AECE decision saved: {decision.get('decision_id')}")
            return {"saved": True, "data": result.data[0] if result.data else None}
        except Exception as e:
            logger.error(f"[Database] Failed to save AECE decision: {e}")
            return {"error": str(e), "saved": False}
    
    @retry_on_failure()
    def save_aece_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Save current AECE state"""
        if not self.available:
            return {"error": "Database not available", "saved": False}
        
        try:
            # Upsert (update if exists, insert if not)
            record = self._prepare_record(state)
            result = self._client.table(Tables.AECE_STATE).upsert(record, on_conflict="state_id").execute()
            logger.debug(f"[Database] AECE state saved")
            return {"saved": True, "data": result.data[0] if result.data else None}
        except Exception as e:
            logger.error(f"[Database] Failed to save AECE state: {e}")
            return {"error": str(e), "saved": False}
    
    @retry_on_failure()
    def get_aece_decisions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent AECE decisions"""
        if not self.available:
            return []
        
        try:
            result = self._client.table(Tables.AECE_DECISIONS)\
                .select("*")\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[Database] Failed to get AECE decisions: {e}")
            return []
    
    @retry_on_failure()
    def get_latest_aece_state(self) -> Optional[Dict[str, Any]]:
        """Get latest AECE state"""
        if not self.available:
            return None
        
        try:
            result = self._client.table(Tables.AECE_STATE)\
                .select("*")\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"[Database] Failed to get AECE state: {e}")
            return None
    
    # ============================================================================
    # PARTNER MANAGEMENT
    # ============================================================================
    
    @retry_on_failure()
    def save_partner(self, partner_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save partner record"""
        if not self.available:
            return {"error": "Database not available", "saved": False}
        
        try:
            record = self._prepare_record(partner_data)
            result = self._client.table(Tables.PARTNERS).insert(record).execute()
            logger.info(f"[Database] Partner saved: {partner_data.get('partner_id')}")
            return {"saved": True, "data": result.data[0] if result.data else None}
        except Exception as e:
            logger.error(f"[Database] Failed to save partner: {e}")
            return {"error": str(e), "saved": False}
    
    @retry_on_failure()
    def get_partners(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all partners"""
        if not self.available:
            return []
        
        try:
            result = self._client.table(Tables.PARTNERS).select("*").limit(limit).execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[Database] Failed to get partners: {e}")
            return []
    
    @retry_on_failure()
    def get_partner_by_id(self, partner_id: str) -> Optional[Dict[str, Any]]:
        """Get partner by ID"""
        if not self.available:
            return None
        
        try:
            result = self._client.table(Tables.PARTNERS).select("*").eq("partner_id", partner_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"[Database] Failed to get partner: {e}")
            return None
    
    # ============================================================================
    # WEATHER DATA
    # ============================================================================
    
    @retry_on_failure()
    def save_weather_data(self, weather_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save weather data"""
        if not self.available:
            return {"error": "Database not available", "saved": False}
        
        try:
            record = self._prepare_record(weather_data)
            result = self._client.table(Tables.WEATHER_DATA).insert(record).execute()
            logger.debug(f"[Database] Weather data saved")
            return {"saved": True, "data": result.data[0] if result.data else None}
        except Exception as e:
            logger.error(f"[Database] Failed to save weather data: {e}")
            return {"error": str(e), "saved": False}
    
    @retry_on_failure()
    def get_weather_data(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent weather data"""
        if not self.available:
            return []
        
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            result = self._client.table(Tables.WEATHER_DATA)\
                .select("*")\
                .gte("created_at", cutoff)\
                .order("created_at", desc=True)\
                .execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[Database] Failed to get weather data: {e}")
            return []
    
    # ============================================================================
    # AUDIT LOGS
    # ============================================================================
    
    @retry_on_failure()
    def log_audit_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Log audit event"""
        if not self.available:
            return {"error": "Database not available", "saved": False}
        
        try:
            record = self._prepare_record(event)
            result = self._client.table(Tables.AUDIT_LOGS).insert(record).execute()
            return {"saved": True, "data": result.data[0] if result.data else None}
        except Exception as e:
            logger.error(f"[Database] Failed to log audit event: {e}")
            return {"error": str(e), "saved": False}
    
    @retry_on_failure()
    def get_audit_logs(self, limit: int = 100, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get audit logs"""
        if not self.available:
            return []
        
        try:
            query = self._client.table(Tables.AUDIT_LOGS).select("*")
            
            if user_id:
                query = query.eq("user_id", user_id)
            
            result = query.order("created_at", desc=True).limit(limit).execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[Database] Failed to get audit logs: {e}")
            return []
    
    # ============================================================================
    # PREDICTIONS
    # ============================================================================
    
    @retry_on_failure()
    def save_prediction(self, prediction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save prediction record"""
        if not self.available:
            return {"error": "Database not available", "saved": False}
        
        try:
            record = self._prepare_record(prediction_data)
            result = self._client.table(Tables.PREDICTIONS).insert(record).execute()
            logger.debug(f"[Database] Prediction saved")
            return {"saved": True, "data": result.data[0] if result.data else None}
        except Exception as e:
            logger.error(f"[Database] Failed to save prediction: {e}")
            return {"error": str(e), "saved": False}
    
    @retry_on_failure()
    def get_predictions(self, sector: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get predictions"""
        if not self.available:
            return []
        
        try:
            query = self._client.table(Tables.PREDICTIONS).select("*")
            
            if sector:
                query = query.eq("sector", sector)
            
            result = query.order("created_at", desc=True).limit(limit).execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[Database] Failed to get predictions: {e}")
            return []
    
    # ============================================================================
    # STORAGE
    # ============================================================================
    
    def upload_report(self, file_path: str, file_content: bytes, content_type: str = "application/pdf") -> Optional[str]:
        """Upload report to storage bucket"""
        if not self.available:
            return None
        
        try:
            storage = self._client.storage()
            bucket = storage.from_(SUPABASE_STORAGE_BUCKET)
            
            # Upload file
            bucket.upload(file_path, file_content, {"content-type": content_type})
            
            # Get public URL
            public_url = bucket.get_public_url(file_path)
            logger.info(f"[Database] Report uploaded: {file_path}")
            return public_url
        except Exception as e:
            logger.error(f"[Database] Failed to upload report: {e}")
            return None
    
    def get_report_url(self, file_path: str) -> Optional[str]:
        """Get public URL for report"""
        if not self.available:
            return None
        
        try:
            storage = self._client.storage()
            bucket = storage.from_(SUPABASE_STORAGE_BUCKET)
            return bucket.get_public_url(file_path)
        except Exception as e:
            logger.error(f"[Database] Failed to get report URL: {e}")
            return None
    
    # ============================================================================
    # REAL-TIME SUBSCRIPTIONS
    # ============================================================================
    
    def subscribe_to_table(self, table: str, callback: Callable, filter: Optional[str] = None) -> str:
        """
        Subscribe to real-time changes on a table.
        
        Args:
            table: Table name to subscribe to
            callback: Function to call on change (receives payload)
            filter: Optional filter (e.g., "sector=eq.renewables")
        
        Returns:
            Subscription ID
        """
        if not self.available:
            logger.warning("[Database] Cannot subscribe - database not available")
            return ""
        
        try:
            subscription_id = f"{table}_{id(callback)}"
            
            # Build channel name
            channel_name = f"realtime:{table}"
            if filter:
                channel_name = f"realtime:{table}:{filter}"
            
            # Create channel
            channel = self._client.realtime.channel(channel_name)
            
            # Handle changes
            def handle_change(payload):
                asyncio.create_task(callback(payload))
            
            # Subscribe to changes
            channel.on("INSERT", callback=handle_change)
            channel.on("UPDATE", callback=handle_change)
            channel.on("DELETE", callback=handle_change)
            channel.subscribe()
            
            self._realtime_subscriptions[subscription_id] = channel
            logger.info(f"[Database] Subscribed to {table}")
            return subscription_id
            
        except Exception as e:
            logger.error(f"[Database] Failed to subscribe: {e}")
            return ""
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from real-time updates"""
        if subscription_id in self._realtime_subscriptions:
            try:
                channel = self._realtime_subscriptions[subscription_id]
                channel.unsubscribe()
                del self._realtime_subscriptions[subscription_id]
                logger.info(f"[Database] Unsubscribed: {subscription_id}")
                return True
            except Exception as e:
                logger.error(f"[Database] Failed to unsubscribe: {e}")
        return False
    
    # ============================================================================
    # HEALTH CHECK
    # ============================================================================
    
    def health_check(self) -> Dict[str, Any]:
        """Check database connectivity"""
        if not self.available:
            return {
                "status": "unavailable",
                "error": "Not configured or connection failed",
                "url": SUPABASE_URL
            }
        
        try:
            # Simple query to test connection
            result = self._client.table(Tables.SIMULATIONS).select("count").limit(1).execute()
            return {
                "status": "healthy",
                "url": SUPABASE_URL,
                "bucket": SUPABASE_STORAGE_BUCKET,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "url": SUPABASE_URL
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        if not self.available:
            return {"available": False}
        
        try:
            # Get counts from main tables
            sim_count = len(self._client.table(Tables.SIMULATIONS).select("count").execute().data or [])
            energy_count = len(self._client.table(Tables.ENERGY_DATA).select("count").execute().data or [])
            adfi_count = len(self._client.table(Tables.ADFI_INJECTIONS).select("count").execute().data or [])
            aece_count = len(self._client.table(Tables.AECE_DECISIONS).select("count").execute().data or [])
            
            return {
                "available": True,
                "counts": {
                    "simulations": sim_count,
                    "energy_data": energy_count,
                    "adfi_injections": adfi_count,
                    "aece_decisions": aece_count,
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"[Database] Failed to get stats: {e}")
            return {"available": True, "error": str(e)}


# ============================================================================
# GLOBAL INSTANCES
# ============================================================================

supabase_client = SupabaseClient()


def get_db() -> SupabaseClient:
    """Get database client instance"""
    return supabase_client


def get_supabase_client() -> SupabaseClient:
    """Get Supabase client (alias)"""
    return supabase_client


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'SupabaseClient',
    'get_db',
    'get_supabase_client',
    'supabase_client',
    'Tables',
]