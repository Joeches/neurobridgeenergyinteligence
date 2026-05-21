from __future__ import annotations

import secrets
import time
from typing import Dict, Any

from backend.core.api_key_manager import get_api_key_manager, ApiPlan


def rotate_external_client_key(client_id: str) -> Dict[str, Any]:
    manager = get_api_key_manager()

    old_client = manager.get_client(client_id)
    if not old_client:
        return {
            "status": "not_found",
            "client_id": client_id,
            "rotated": False,
            "timestamp": int(time.time()),
        }

    manager.deactivate_client(client_id)

    new_key = f"nb11d_{secrets.token_urlsafe(32)}"
    new_client_id = f"{client_id}_rotated_{secrets.token_hex(4)}"

    client = manager.register_existing_key(
        client_id=new_client_id,
        name=f"{old_client.name} - Rotated",
        raw_key=new_key,
        plan=ApiPlan(old_client.plan.value),
        metadata={
            **old_client.metadata,
            "rotated_from": client_id,
            "rotation_reason": "exposed_key",
        },
    )

    return {
        "status": "success",
        "rotated": True,
        "old_client_id": client_id,
        "new_client_id": client.client_id,
        "new_api_key": new_key,
        "plan": client.plan.value,
        "timestamp": int(time.time()),
    }