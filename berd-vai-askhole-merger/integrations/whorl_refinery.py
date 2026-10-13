"""Loopback-only bridge to Whorl refinery service (governed)."""
from __future__ import annotations
import http.client
import json
from typing import Any, Dict, List

BASE_HOST = "127.0.0.1"
BASE_PORT = 8765

def health() -> bool:
    try:
        conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=0.3)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        status = (resp.status == 200)
        conn.close()
        return status
    except Exception:
        return False

def list_models() -> List[str]:
    try:
        conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=1.0)
        conn.request("GET", "/models")
        resp = conn.getresponse()
        data = json.loads(resp.read().decode())
        conn.close()
        return data.get("models", [])
    except Exception:
        return []

def generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=120)
        conn.request(
            "POST", 
            "/skills/refinery/generate", 
            body=json.dumps(payload), 
            headers={"Content-Type": "application/json"}
        )
        resp = conn.getresponse()
        data = json.loads(resp.read().decode())
        conn.close()
        return data
    except Exception as e:
        return {"status": "error", "error": f"Bridge communication failure: {e}"}
