from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from database import get_supabase
from services.auth_service import get_current_user, get_user_id_from_token
from services.alert_service import alert_manager
from models.alert import AlertResponse, AlertSettingsUpdate, AlertSettingsResponse

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
def get_alerts(
    limit: int = 50,
    unread_only: bool = False,
    current_user: dict = Depends(get_current_user),
):
    db = get_supabase()
    query = (
        db.table("alerts")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("created_at", desc=True)
        .limit(limit)
    )
    if unread_only:
        query = query.eq("is_read", False)

    result = query.execute()
    return result.data or []


@router.patch("/{alert_id}/read")
def mark_read(alert_id: str, current_user: dict = Depends(get_current_user)):
    db = get_supabase()
    db.table("alerts").update({"is_read": True}).eq("id", alert_id).eq(
        "user_id", current_user["id"]
    ).execute()
    return {"status": "ok"}


@router.post("/read-all")
def mark_all_read(current_user: dict = Depends(get_current_user)):
    db = get_supabase()
    db.table("alerts").update({"is_read": True}).eq("user_id", current_user["id"]).execute()
    return {"status": "ok"}


@router.get("/settings", response_model=AlertSettingsResponse)
def get_settings(current_user: dict = Depends(get_current_user)):
    db = get_supabase()
    result = db.table("alert_settings").select("*").eq("user_id", current_user["id"]).execute()
    if not result.data:
        # Stwórz domyślne
        new = db.table("alert_settings").insert({"user_id": current_user["id"]}).execute()
        return new.data[0]
    return result.data[0]


@router.patch("/settings", response_model=AlertSettingsResponse)
def update_settings(
    data: AlertSettingsUpdate,
    current_user: dict = Depends(get_current_user),
):
    db = get_supabase()
    updates = data.model_dump(exclude_none=True)
    result = (
        db.table("alert_settings")
        .update(updates)
        .eq("user_id", current_user["id"])
        .execute()
    )
    return result.data[0]


@router.websocket("/ws")
async def alerts_websocket(websocket: WebSocket, token: str = Query(...)):
    """WebSocket do odbierania push notyfikacji alertów."""
    try:
        user_id = get_user_id_from_token(token)
    except Exception:
        await websocket.close(code=4001)
        return

    await alert_manager.connect(user_id, websocket)
    try:
        # Wyślij nieprzeczytane alerty zaraz po połączeniu
        db = get_supabase()
        unread = (
            db.table("alerts")
            .select("*")
            .eq("user_id", user_id)
            .eq("is_read", False)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        for alert in (unread.data or []):
            await websocket.send_json({"type": "alert", "data": alert})

        # Trzymaj połączenie otwarte
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await alert_manager.disconnect(user_id)
