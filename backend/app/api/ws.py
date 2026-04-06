"""WebSocket endpoint for live test run progress updates."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# In-memory store of active connections per run_id
_connections: dict[str, list[WebSocket]] = {}


async def broadcast_progress(run_id: str, data: dict):
    """Broadcast progress update to all connected clients for a run."""
    connections = _connections.get(run_id, [])
    dead = []
    for ws in connections:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connections.remove(ws)


@router.websocket("/runs/{run_id}")
async def run_progress_ws(websocket: WebSocket, run_id: str):
    """WebSocket for streaming live test run progress.

    Sends JSON messages:
    - {"type": "progress", "completed": N, "total": M, "pct": 0-100}
    - {"type": "result", "test_case_id": "...", "score": 0.85, "passed": true}
    - {"type": "error", "test_case_id": "...", "error": "..."}
    - {"type": "completed", "summary": {...}}
    """
    await websocket.accept()

    if run_id not in _connections:
        _connections[run_id] = []
    _connections[run_id].append(websocket)

    try:
        # Keep connection alive, handle client messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Client can send "ping" to keep alive
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    finally:
        if run_id in _connections:
            _connections[run_id] = [
                ws for ws in _connections[run_id] if ws != websocket
            ]
