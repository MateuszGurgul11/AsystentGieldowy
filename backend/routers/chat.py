import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from database import get_supabase
from services.auth_service import get_current_user, get_user_id_from_token
from services.portfolio_service import build_portfolio_response
from llm.scenario_generator import generate_chat_response

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/history")
def get_history(
    session_id: str | None = None,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Pobiera historię chatu (ostatnią sesję lub podaną session_id)."""
    db = get_supabase()
    query = (
        db.table("chat_messages")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("created_at", desc=False)
        .limit(limit)
    )
    if session_id:
        query = query.eq("session_id", session_id)

    result = query.execute()
    return {"messages": result.data or []}


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket, token: str = Query(...)):
    """
    WebSocket chat z agentem.
    Klient wysyła: {"message": "treść", "session_id": "opcjonalne-uuid"}
    Serwer odpowiada strumieniowo tokenami, potem {"done": true}
    """
    await websocket.accept()

    try:
        user_id = get_user_id_from_token(token)
    except Exception:
        await websocket.send_json({"type": "error", "message": "Nieprawidłowy token"})
        await websocket.close(code=4001)
        return

    db = get_supabase()

    # Pobierz profil użytkownika
    profile_result = db.table("profiles").select("*").eq("id", user_id).execute()
    user = profile_result.data[0] if profile_result.data else {}

    try:
        while True:
            raw = await websocket.receive_json()
            user_message = raw.get("message", "").strip()
            session_id = raw.get("session_id") or str(uuid.uuid4())

            if not user_message:
                continue

            # Zapisz wiadomość użytkownika
            db.table("chat_messages").insert({
                "user_id": user_id,
                "session_id": session_id,
                "role": "user",
                "content": user_message,
            }).execute()

            # Zbierz kontekst
            portfolio_raw = (
                db.table("portfolios")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            portfolio = {}
            if portfolio_raw.data:
                portfolio = build_portfolio_response(portfolio_raw.data[0]).model_dump()

            # Ostatnie dane rynkowe
            market_result = (
                db.table("market_snapshots")
                .select("symbol, price_pln, price_change_24h, rsi_14")
                .order("snapshot_at", desc=True)
                .limit(100)
                .execute()
            )
            seen = set()
            market_data = {}
            for row in (market_result.data or []):
                sym = row["symbol"]
                if sym not in seen:
                    seen.add(sym)
                    market_data[sym] = row

            # Ostatnie alerty
            alerts_result = (
                db.table("alerts")
                .select("title, body, priority")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(3)
                .execute()
            )
            recent_alerts = alerts_result.data or []

            # Wyślij "typing..."
            await websocket.send_json({"type": "typing"})

            # Generuj odpowiedź LLM
            response_text = await generate_chat_response(
                user_message=user_message,
                portfolio=portfolio,
                budget_pln=float(user.get("budget_pln", 0)),
                risk_profile=user.get("risk_profile", "medium"),
                market_data=market_data,
                recent_alerts=recent_alerts,
            )

            # Wyślij odpowiedź
            await websocket.send_json({
                "type": "message",
                "role": "assistant",
                "content": response_text,
                "session_id": session_id,
            })

            # Zapisz odpowiedź do historii
            db.table("chat_messages").insert({
                "user_id": user_id,
                "session_id": session_id,
                "role": "assistant",
                "content": response_text,
                "context": {
                    "budget_pln": user.get("budget_pln"),
                    "risk_profile": user.get("risk_profile"),
                    "market_symbols": list(market_data.keys())[:10],
                },
            }).execute()

            await websocket.send_json({"type": "done", "session_id": session_id})

    except WebSocketDisconnect:
        pass
