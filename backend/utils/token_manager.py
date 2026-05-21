"""
================================================================================
Project: NeuroBridge 11D Energy Intelligence Kernel
Component: Token Manager - Enterprise Session Management
Version: 1.0.0
Description: Manages quantum session tokens with auto-refresh capabilities
================================================================================
"""

import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import set_key, load_dotenv

logger = logging.getLogger("TokenManager")

class TokenManager:
    """Enterprise token manager with auto-refresh and file sync"""
    
    def __init__(self):
        self.env_path = Path(__file__).parent.parent.parent / '.env'
        self.current_token = None
        self.session_expiry = None
        self.refresh_thread = None
        self.refresh_active = False
        self.refresh_threshold_minutes = 5
        
        # Load or create token
        self._load_or_create_token()
        
        logger.info(f"Token Manager initialized | Token: {self.current_token[:12] if self.current_token else 'None'}...")
    
    def _load_or_create_token(self):
        """Load existing token or create new one"""
        # Load from environment
        load_dotenv(self.env_path)
        
        token = os.getenv("CTO_ACCESS_CODE")
        expiry_str = os.getenv("SESSION_EXPIRY")
        
        if token and token != "DEV-ABUJA-PILOT-2026":
            self.current_token = token
            if expiry_str:
                try:
                    self.session_expiry = datetime.fromisoformat(expiry_str)
                except:
                    self.session_expiry = datetime.now(timezone.utc) + timedelta(minutes=55)
            else:
                self.session_expiry = datetime.now(timezone.utc) + timedelta(minutes=55)
            logger.info(f"✅ Using existing valid token: {token[:12]}...")
        else:
            # Generate new token
            self._generate_new_token()
    
    def _generate_new_token(self):
        """Generate a new CTO-format token"""
        import secrets
        import hashlib
        
        # Generate random components
        parts = []
        for _ in range(4):
            parts.append(secrets.token_hex(2).upper())
        
        # Format: CTO-XXXX-XXXX-XXXX-XXXX
        token = f"CTO-{parts[0]}-{parts[1]}-{parts[2]}-{parts[3]}"
        
        # Set expiry (55 minutes from now)
        self.session_expiry = datetime.now(timezone.utc) + timedelta(minutes=55)
        
        # Save to .env
        self._save_to_env(token, self.session_expiry)
        
        self.current_token = token
        logger.info(f"✅ Generated new token: {token[:12]}...")
    
    def _save_to_env(self, token: str, expiry: datetime):
        """Save token to .env file"""
        try:
            set_key(str(self.env_path), "CTO_ACCESS_CODE", token)
            set_key(str(self.env_path), "SESSION_EXPIRY", expiry.isoformat())
            
            # Also update frontend sync files
            self._sync_frontend_files(token, expiry)
            
            logger.info(f"✅ .env updated with token: {token[:12]}...")
        except Exception as e:
            logger.error(f"Failed to save token: {e}")
    
    def _sync_frontend_files(self, token: str, expiry: datetime):
        """Sync token to frontend static files"""
        static_dir = Path(__file__).parent.parent.parent / "frontend" / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON sync file
        sync_data = {
            "token": token,
            "expires_at": expiry.isoformat(),
            "security_level": "LATTICE-256",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        sync_file = static_dir / "token_sync.json"
        with open(sync_file, 'w') as f:
            json.dump(sync_data, f, indent=2)
        logger.info(f"✅ Frontend sync file created at: {sync_file}")
        
        # JavaScript token file
        js_content = f"""// Auto-generated token file - DO NOT EDIT
window.NEUROBRIDGE_CONFIG = {{
    token: "{token}",
    expiresAt: "{expiry.isoformat()}",
    securityLevel: "LATTICE-256",
    updatedAt: "{datetime.now(timezone.utc).isoformat()}"
}};
"""
        js_file = static_dir / "env.js"
        with open(js_file, 'w') as f:
            f.write(js_content)
        logger.info(f"✅ JavaScript token file created: {js_file}")
    
    def get_current_token(self) -> Optional[str]:
        """Get current active token"""
        # Check if token is about to expire
        if self.session_expiry:
            time_remaining = (self.session_expiry - datetime.now(timezone.utc)).total_seconds()
            if time_remaining < 60:  # Less than 1 minute
                logger.warning("Token about to expire, refreshing...")
                self._generate_new_token()
        
        return self.current_token
    
    def get_session_expiry(self) -> Optional[datetime]:
        """Get session expiry time"""
        return self.session_expiry
    
    def start_auto_refresh(self):
        """Start auto-refresh thread"""
        if self.refresh_thread and self.refresh_thread.is_alive():
            return
        
        self.refresh_active = True
        self.refresh_thread = threading.Thread(target=self._auto_refresh_loop, daemon=True)
        self.refresh_thread.start()
        logger.info("🚀 Auto-token refresh thread started")
    
    def stop_auto_refresh(self):
        """Stop auto-refresh thread"""
        self.refresh_active = False
        if self.refresh_thread:
            self.refresh_thread.join(timeout=2)
        logger.info("🛑 Auto-token refresh stopped")
    
    def _auto_refresh_loop(self):
        """Background thread for token refresh"""
        while self.refresh_active:
            time.sleep(60)  # Check every minute
            
            if self.session_expiry:
                time_remaining = (self.session_expiry - datetime.now(timezone.utc)).total_seconds()
                refresh_threshold_seconds = self.refresh_threshold_minutes * 60
                
                if time_remaining < refresh_threshold_seconds and time_remaining > 0:
                    logger.info(f"Auto-refreshing token (expires in {time_remaining/60:.0f} minutes)")
                    self._generate_new_token()

# Singleton instance
_token_manager = None

def get_token_manager() -> TokenManager:
    """Get or create token manager singleton"""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager