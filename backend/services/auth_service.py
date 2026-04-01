from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_supabase

bearer_scheme = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    """
    Weryfikuje Supabase JWT token i zwraca dane użytkownika z profiles.
    """
    token = credentials.credentials
    return _resolve_user(token)


def get_user_id_from_token(token: str) -> str:
    """Weryfikuje token i zwraca user_id. Używane w WebSocket handlerach."""
    db = get_supabase()
    try:
        response = db.auth.get_user(token)
        if not response.user:
            raise ValueError("Brak usera")
        return response.user.id
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy token")


def _resolve_user(token: str) -> dict:
    """Weryfikuje token Supabase i łączy dane auth + profile."""
    db = get_supabase()
    try:
        auth_response = db.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy token")

    if not auth_response.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy token")

    auth_user = auth_response.user
    user_id = auth_user.id

    # Pobierz dodatkowe dane z profiles
    profile_result = db.table("profiles").select("*").eq("id", user_id).execute()
    profile = profile_result.data[0] if profile_result.data else {}

    return {
        "id": user_id,
        "email": auth_user.email,
        "risk_profile": profile.get("risk_profile", "medium"),
        "budget_pln": profile.get("budget_pln", 0),
        "preferred_currency": profile.get("preferred_currency", "PLN"),
        "created_at": str(auth_user.created_at),
    }
