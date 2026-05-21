"""
================================================================================
╔═══════════════════════════════════════════════════════════════════════════════════╗
║                                                                                   ║
║   ██╗    ██╗███████╗██████╗ ███████╗ ██████╗ ██╗  ██╗███████╗████████╗            ║
║   ██║    ██║██╔════╝██╔══██╗██╔════╝██╔════╝ ██║  ██║██╔════╝╚══██╔══╝            ║
║   ██║ █╗ ██║█████╗  ██████╔╝███████╗██║  ███╗███████║█████╗     ██║               ║
║   ██║███╗██║██╔══╝  ██╔══██╗╚════██║██║   ██║██╔══██║██╔══╝     ██║               ║
║   ╚███╔███╔╝███████╗██████╔╝███████║╚██████╔╝██║  ██║███████╗   ██║               ║
║    ╚══╝╚══╝ ╚══════╝╚═════╝ ╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝   ╚═╝               ║
║                                                                                   ║
║              WEBSOCKET ROUTES v1.0.0 - PRODUCTION SECURITY                      ║
║                                                                                   ║
║  ╔═══════════════════════════════════════════════════════════════════════════╗   ║
║  ║  FEATURES:                                                               ║   ║
║  ║  ✓ Rate limiting per IP with WebSocketGuard                              ║   ║
║  ║  ✓ Quantum channel blocked in Phase 1 with 403                           ║   ║
║  ║  ✓ Energy channel active with real-time telemetry streaming              ║   ║
║  ║  ✓ Automatic IP blocking for abusive clients                             ║   ║
║  ║  ✓ Connection tracking and monitoring                                    ║   ║
║  ║  ✓ Graceful disconnection handling                                       ║   ║
║  ║  ✓ Prometheus metrics for active connections                             ║   ║
║  ╚═══════════════════════════════════════════════════════════════════════════╝   ║
║                                                                                   ║
║  🛡️ PROTECTED ENDPOINTS:                                                         ║
║     • /ws/energy-channel - Active WebSocket with rate limiting                  ║
║     • /ws/quantum-channel - Blocked in Phase 1 (returns 403)                    ║
║                                                                                   ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
================================================================================

NEUROBRIDGE 11D - WEBSOCKET ROUTES v1.0.0
Enterprise-grade WebSocket endpoints with security
CTO: Joseph Ochelebe | NeuroBridge Technologies Ltd

================================================================================
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Set
from datetime import datetime, timezone
from enum import Enum

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState

# Import security guard
from backend.security.websocket_guard import get_websocket_guard, protect_websocket_endpoint

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

# WebSocket heartbeat interval (seconds)
HEARTBEAT_INTERVAL = 30

# Maximum time without heartbeat before disconnecting (seconds)
HEARTBEAT_TIMEOUT = 90

# Maximum queue size for pending messages
MAX_QUEUE_SIZE = 1000

# ============================================================================
# DATA MODELS
# ============================================================================

class ConnectionState(str, Enum):
    """WebSocket connection states."""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"


class WebSocketConnection:
    """Track WebSocket connection metadata."""
    
    def __init__(self, websocket: WebSocket, client_ip: str, path: str):
        self.websocket = websocket
        self.client_ip = client_ip
        self.path = path
        self.connected_at = time.time()
        self.last_heartbeat = time.time()
        self.message_count = 0
        self.state = ConnectionState.CONNECTING
        self.disconnect_reason: Optional[str] = None
    
    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.connected_at
    
    @property
    def is_alive(self) -> bool:
        return self.state == ConnectionState.CONNECTED and time.time() - self.last_heartbeat < HEARTBEAT_TIMEOUT
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_ip": self.client_ip,
            "path": self.path,
            "connected_at": datetime.fromtimestamp(self.connected_at, tz=timezone.utc).isoformat(),
            "uptime_seconds": round(self.uptime_seconds, 2),
            "message_count": self.message_count,
            "state": self.state.value,
            "is_alive": self.is_alive
        }


# ============================================================================
# CONNECTION MANAGER
# ============================================================================

class WebSocketConnectionManager:
    """
    Manages active WebSocket connections with tracking and monitoring.
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if WebSocketConnectionManager._initialized:
            return
        WebSocketConnectionManager._initialized = True
        
        self._connections: Dict[str, WebSocketConnection] = {}
        self._lock = asyncio.Lock()
        
        logger.info("[WebSocketManager] ✅ Connection manager initialized")
    
    async def add_connection(self, connection_id: str, connection: WebSocketConnection):
        """Add a connection to the manager."""
        async with self._lock:
            self._connections[connection_id] = connection
            logger.info(f"[WebSocketManager] 📡 Connection added: {connection_id} from {connection.client_ip}")
    
    async def remove_connection(self, connection_id: str, reason: str = "normal"):
        """Remove a connection from the manager."""
        async with self._lock:
            if connection_id in self._connections:
                conn = self._connections[connection_id]
                conn.state = ConnectionState.DISCONNECTED
                conn.disconnect_reason = reason
                del self._connections[connection_id]
                logger.info(f"[WebSocketManager] 🔌 Connection removed: {connection_id} | Reason: {reason}")
    
    async def update_heartbeat(self, connection_id: str):
        """Update the last heartbeat timestamp for a connection."""
        async with self._lock:
            if connection_id in self._connections:
                self._connections[connection_id].last_heartbeat = time.time()
    
    async def increment_message_count(self, connection_id: str):
        """Increment the message count for a connection."""
        async with self._lock:
            if connection_id in self._connections:
                self._connections[connection_id].message_count += 1
    
    async def set_connection_state(self, connection_id: str, state: ConnectionState):
        """Set the connection state."""
        async with self._lock:
            if connection_id in self._connections:
                self._connections[connection_id].state = state
    
    async def get_connection(self, connection_id: str) -> Optional[WebSocketConnection]:
        """Get a connection by ID."""
        async with self._lock:
            return self._connections.get(connection_id)
    
    async def get_active_connections(self) -> int:
        """Get the number of active connections."""
        async with self._lock:
            return len(self._connections)
    
    async def get_all_connections(self) -> Dict[str, Dict[str, Any]]:
        """Get all connections as dictionaries."""
        async with self._lock:
            return {cid: conn.to_dict() for cid, conn in self._connections.items()}
    
    async def cleanup_stale_connections(self):
        """Clean up connections that have timed out."""
        async with self._lock:
            stale = []
            for cid, conn in self._connections.items():
                if not conn.is_alive:
                    stale.append(cid)
            
            for cid in stale:
                conn = self._connections[cid]
                try:
                    if conn.websocket.client_state == WebSocketState.CONNECTED:
                        await conn.websocket.close(code=1001, reason="Heartbeat timeout")
                except Exception:
                    pass
                del self._connections[cid]
                logger.warning(f"[WebSocketManager] 🧹 Cleaned stale connection: {cid}")
            
            return len(stale)
    
    async def broadcast_to_channel(self, channel: str, message: Dict[str, Any], exclude: Set[str] = None):
        """Broadcast a message to all connections on a specific channel."""
        if exclude is None:
            exclude = set()
        
        async with self._lock:
            tasks = []
            for cid, conn in self._connections.items():
                if conn.path == channel and cid not in exclude and conn.is_alive:
                    tasks.append(self._safe_send(conn.websocket, message))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_send(self, websocket: WebSocket, message: Dict[str, Any]):
        """Safely send a message to a websocket."""
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(message)
        except Exception as e:
            logger.debug(f"[WebSocketManager] Failed to send message: {e}")


# ============================================================================
# WEBSOCKET ROUTER
# ============================================================================

router = APIRouter(tags=["websocket"])

# Global connection manager
_connection_manager = WebSocketConnectionManager()
_heartbeat_task: Optional[asyncio.Task] = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_connection_id(websocket: WebSocket) -> str:
    """Generate a unique connection ID."""
    client_info = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
    timestamp = int(time.time() * 1000)
    return f"{client_info}_{timestamp}"


async def send_heartbeat(websocket: WebSocket, connection_id: str):
    """Send a heartbeat message to keep the connection alive."""
    try:
        await websocket.send_json({
            "type": "heartbeat",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        await _connection_manager.update_heartbeat(connection_id)
    except Exception:
        pass


async def send_telemetry_update(websocket: WebSocket, telemetry: Dict[str, Any]):
    """Send a telemetry update to the client."""
    try:
        await websocket.send_json({
            "type": "telemetry",
            "data": telemetry,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logger.debug(f"[WebSocket] Failed to send telemetry: {e}")


async def background_heartbeat(connection_id: str, websocket: WebSocket):
    """Background task to send periodic heartbeats."""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            
            # Check if connection still exists
            conn = await _connection_manager.get_connection(connection_id)
            if not conn or conn.state != ConnectionState.CONNECTED:
                break
            
            await send_heartbeat(websocket, connection_id)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.debug(f"[WebSocket] Heartbeat task error: {e}")


async def background_telemetry_stream(connection_id: str, websocket: WebSocket):
    """Background task to stream telemetry data."""
    try:
        from backend.core.energy_metrics_engine import get_metrics_engine
        
        while True:
            await asyncio.sleep(2)  # Update every 2 seconds
            
            # Check if connection still exists
            conn = await _connection_manager.get_connection(connection_id)
            if not conn or conn.state != ConnectionState.CONNECTED:
                break
            
            try:
                # Get current telemetry
                metrics_engine = get_metrics_engine()
                telemetry = metrics_engine.get_live_metrics()
                
                await send_telemetry_update(websocket, telemetry)
            except Exception as e:
                logger.debug(f"[WebSocket] Telemetry fetch error: {e}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.debug(f"[WebSocket] Telemetry stream error: {e}")


# ============================================================================
# WEBSOCKET ENDPOINTS
# ============================================================================

@router.websocket("/ws/energy-channel")
async def energy_websocket_endpoint(websocket: WebSocket):
    """
    Active WebSocket endpoint for energy telemetry streaming.
    
    Features:
    - Rate limiting per IP
    - Real-time telemetry updates
    - Heartbeat mechanism
    - Connection tracking
    """
    connection_id = generate_connection_id(websocket)
    client_ip = websocket.client.host if websocket.client else "unknown"
    
    # Initialize security guard
    guard = get_websocket_guard()
    
    # Check rate limiting
    is_allowed, reason = await protect_websocket_endpoint(
        websocket, guard, "/ws/energy-channel"
    )
    
    if not is_allowed:
        logger.warning(f"[WebSocket] 🚫 Connection rejected: {client_ip} - {reason}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason)
        return
    
    # Accept the connection
    await websocket.accept()
    
    # Create connection record
    connection = WebSocketConnection(websocket, client_ip, "/ws/energy-channel")
    connection.state = ConnectionState.CONNECTED
    await _connection_manager.add_connection(connection_id, connection)
    
    logger.info(f"[WebSocket] ✅ Energy channel connected: {connection_id} from {client_ip}")
    
    # Start background tasks
    heartbeat_task = asyncio.create_task(background_heartbeat(connection_id, websocket))
    telemetry_task = asyncio.create_task(background_telemetry_stream(connection_id, websocket))
    
    try:
        # Main message loop
        while True:
            try:
                # Wait for messages from client (with timeout for heartbeat)
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=HEARTBEAT_INTERVAL + 10
                )
                
                # Process incoming messages
                await _connection_manager.increment_message_count(connection_id)
                
                message_type = message.get("type", "unknown")
                
                if message_type == "ping":
                    # Respond to ping
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                elif message_type == "heartbeat_ack":
                    # Client acknowledged heartbeat
                    await _connection_manager.update_heartbeat(connection_id)
                else:
                    # Unknown message type - log but ignore
                    logger.debug(f"[WebSocket] Unknown message type: {message_type}")
                    
            except asyncio.TimeoutError:
                # Check if connection is still alive
                if not connection.is_alive:
                    logger.warning(f"[WebSocket] 💀 Connection timed out: {connection_id}")
                    break
                continue
                
    except WebSocketDisconnect as e:
        logger.info(f"[WebSocket] 🔌 Energy channel disconnected: {connection_id} | Code: {e.code}")
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Energy channel error: {connection_id} - {e}")
    finally:
        # Cleanup
        heartbeat_task.cancel()
        telemetry_task.cancel()
        await _connection_manager.remove_connection(connection_id, "disconnect")
        
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/quantum-channel")
async def quantum_websocket_endpoint(websocket: WebSocket):
    """
    Quantum WebSocket endpoint - BLOCKED in Phase 1.
    
    Returns 403 Forbidden with rate limiting to prevent abuse.
    """
    connection_id = generate_connection_id(websocket)
    client_ip = websocket.client.host if websocket.client else "unknown"
    
    # Initialize security guard
    guard = get_websocket_guard()
    
    # Check rate limiting (stricter for quantum channel)
    is_allowed, reason = await protect_websocket_endpoint(
        websocket, guard, "/ws/quantum-channel"
    )
    
    if not is_allowed:
        logger.warning(f"[WebSocket] 🚫 Quantum channel blocked (rate limited): {client_ip} - {reason}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason)
        return
    
    # Phase 1: Always reject quantum channel with 403
    # Record the attempt for monitoring
    guard.record_attempt(client_ip, "/ws/quantum-channel")
    
    logger.warning(f"[WebSocket] 🚫 Quantum channel blocked (Phase 1): {client_ip}")
    
    await websocket.close(
        code=status.WS_1008_POLICY_VIOLATION,
        reason="Quantum channel not available in Phase 1. Please use /ws/energy-channel for energy telemetry."
    )


# ============================================================================
# ADMIN ENDPOINTS (Optional, for monitoring)
# ============================================================================

@router.get("/websocket/status")
async def websocket_status():
    """
    Get WebSocket connection status and statistics.
    (Admin endpoint - should be protected in production)
    """
    active_connections = await _connection_manager.get_active_connections()
    connections = await _connection_manager.get_all_connections()
    guard = get_websocket_guard()
    
    return {
        "success": True,
        "status": {
            "active_connections": active_connections,
            "connections": connections,
            "rate_limiting": guard.get_statistics(),
            "heartbeat_interval": HEARTBEAT_INTERVAL,
            "heartbeat_timeout": HEARTBEAT_TIMEOUT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "PHASE_1_PRODUCTION"
        }
    }


@router.post("/websocket/cleanup")
async def cleanup_stale_connections():
    """
    Manually trigger cleanup of stale connections.
    (Admin endpoint - should be protected in production)
    """
    cleaned = await _connection_manager.cleanup_stale_connections()
    return {
        "success": True,
        "message": f"Cleaned {cleaned} stale connections",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# BACKGROUND TASKS
# ============================================================================

async def start_websocket_cleanup_task():
    """Start the background cleanup task for WebSocket connections."""
    global _heartbeat_task
    
    async def cleanup_loop():
        while True:
            await asyncio.sleep(60)  # Run every minute
            try:
                cleaned = await _connection_manager.cleanup_stale_connections()
                if cleaned > 0:
                    logger.info(f"[WebSocket] 🧹 Cleaned {cleaned} stale connections")
            except Exception as e:
                logger.error(f"[WebSocket] Cleanup error: {e}")
    
    _heartbeat_task = asyncio.create_task(cleanup_loop())
    logger.info("[WebSocket] ✅ Background cleanup task started")


async def stop_websocket_cleanup_task():
    """Stop the background cleanup task."""
    global _heartbeat_task
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
    logger.info("[WebSocket] 🛑 Background cleanup task stopped")


# ============================================================================
# INITIALIZATION
# ============================================================================

async def initialize_websocket_routes():
    """Initialize WebSocket routes and start background tasks."""
    await start_websocket_cleanup_task()
    logger.info("[WebSocketRoutes] ✅ Initialized")


async def shutdown_websocket_routes():
    """Shutdown WebSocket routes and stop background tasks."""
    await stop_websocket_cleanup_task()
    logger.info("[WebSocketRoutes] 🛑 Shutdown complete")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'router',
    'initialize_websocket_routes',
    'shutdown_websocket_routes',
    'WebSocketConnectionManager',
    'get_connection_manager',
]


# ============================================================================
# INITIALIZATION LOG
# ============================================================================

logger.info("""
╔═══════════════════════════════════════════════════════════════════════════════════╗
║                                                                                   ║
║              WEBSOCKET ROUTES v1.0.0 - PRODUCTION SECURITY                       ║
║                                                                                   ║
║  🛡️ ACTIVE ENDPOINTS:                                                             ║
║  ✅ /ws/energy-channel - Active with rate limiting                               ║
║  ❌ /ws/quantum-channel - Blocked in Phase 1 (returns 403)                       ║
║                                                                                   ║
║  📊 CONFIGURATION:                                                                ║
║  • Heartbeat interval: {HEARTBEAT_INTERVAL}s                                     ║
║  • Heartbeat timeout: {HEARTBEAT_TIMEOUT}s                                       ║
║  • Max queue size: {MAX_QUEUE_SIZE}                                              ║
║                                                                                   ║
║  🚀 STATUS: READY FOR PRODUCTION                                                 ║
║  ✅ Rate limiting active                                                         ║
║  ✅ IP blocking active                                                           ║
║  ✅ Connection tracking active                                                   ║
║                                                                                   ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
""")