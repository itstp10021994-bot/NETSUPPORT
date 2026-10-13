"""Shared message protocol for the classroom management system.

All communication between the hub, teacher console and student agents is
line-delimited JSON over WebSocket. This module centralises the message type
names and small helpers so that every component speaks the same language.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
ROLE_TEACHER = "teacher"
ROLE_STUDENT = "student"

# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------
# Handshake (client -> hub)
HELLO = "hello"                 # {role, name, room}

# Hub -> teacher
ROSTER = "roster"               # {students: [{id, name, online, locked}]}
STUDENT_JOINED = "student_joined"
STUDENT_LEFT = "student_left"
THUMBNAIL = "thumbnail"         # {student_id, image (base64 jpeg), ts}
ACK = "ack"                     # {student_id, action}

# Teacher -> hub -> student
LOCK = "lock"                   # {targets: [id] | "all"}
UNLOCK = "unlock"               # {targets: [id] | "all"}
MESSAGE = "message"             # {targets, text, title}
REQUEST_THUMBNAILS = "request_thumbnails"  # {fps}

# Student -> hub
STATUS = "status"               # {locked: bool, active_window: str}

# Generic
ERROR = "error"                 # {reason}
PING = "ping"
PONG = "pong"


def make(msg_type: str, **fields: Any) -> str:
    """Serialise a protocol message to a JSON string."""
    payload: Dict[str, Any] = {"type": msg_type, "ts": time.time()}
    payload.update(fields)
    return json.dumps(payload, separators=(",", ":"))


def parse(raw: str) -> Dict[str, Any]:
    """Parse an incoming JSON message, returning a dict with at least 'type'."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {"type": ERROR, "reason": "malformed-json"}
    if not isinstance(data, dict) or "type" not in data:
        return {"type": ERROR, "reason": "missing-type"}
    return data
