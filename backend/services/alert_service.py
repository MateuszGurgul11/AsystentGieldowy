import asyncio
from fastapi import WebSocket
from database import get_supabase


class AlertManager:
    """Zarządza połączeniami WebSocket dla alertów użytkowników."""

    def __init__(self):
        # user_id -> WebSocket
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket):
        # accept() już wywołany w routerze przed walidacją tokenu
        async with self._lock:
            self._connections[user_id] = websocket

    async def disconnect(self, user_id: str):
        async with self._lock:
            self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, payload: dict):
        ws = self._connections.get(user_id)
        if ws:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.disconnect(user_id)

    async def broadcast(self, payload: dict):
        for user_id in list(self._connections.keys()):
            await self.send_to_user(user_id, payload)


# Singleton - współdzielony przez cały proces
alert_manager = AlertManager()


def save_alert(
    user_id: str,
    title: str,
    body: str,
    alert_type: str,
    priority: str = "medium",
    event_id: str | None = None,
    prediction_id: str | None = None,
) -> dict:
    """Zapisuje alert do Supabase i zwraca go."""
    db = get_supabase()
    data = {
        "user_id": user_id,
        "type": alert_type,
        "title": title,
        "body": body,
        "priority": priority,
    }
    if event_id:
        data["event_id"] = event_id
    if prediction_id:
        data["prediction_id"] = prediction_id

    result = db.table("alerts").insert(data).execute()
    return result.data[0] if result.data else {}


async def notify_user(
    user_id: str,
    title: str,
    body: str,
    alert_type: str,
    priority: str = "medium",
    event_id: str | None = None,
    prediction_id: str | None = None,
):
    """Zapisuje alert i wysyła push przez WebSocket jeśli użytkownik podłączony."""
    alert = save_alert(user_id, title, body, alert_type, priority, event_id, prediction_id)
    await alert_manager.send_to_user(user_id, {
        "type": "alert",
        "data": alert,
    })
