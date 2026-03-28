from fastapi import APIRouter, HTTPException, status, Depends
from database import get_supabase
from models.user import UserRegister, UserLogin, TokenResponse, RefreshRequest, UserResponse, UserUpdate
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserRegister):
    db = get_supabase()

    try:
        auth_response = db.auth.sign_up({
            "email": data.email,
            "password": data.password,
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not auth_response.user:
        raise HTTPException(status_code=400, detail="Rejestracja nieudana")

    user_id = auth_response.user.id

    # Aktualizuj profil z risk_profile i budget_pln
    db.table("profiles").upsert({
        "id": user_id,
        "risk_profile": data.risk_profile,
        "budget_pln": data.budget_pln,
    }).execute()

    # Stwórz domyślny portfel
    db.table("portfolios").insert({
        "user_id": user_id,
        "name": "Mój portfel",
        "broker": "manual",
    }).execute()

    # Stwórz domyślne ustawienia alertów
    db.table("alert_settings").upsert({"user_id": user_id}).execute()

    if not auth_response.session:
        raise HTTPException(
            status_code=400,
            detail="Konto założone - potwierdź email przed zalogowaniem"
        )

    return TokenResponse(
        access_token=auth_response.session.access_token,
        refresh_token=auth_response.session.refresh_token,
    )


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin):
    db = get_supabase()

    try:
        auth_response = db.auth.sign_in_with_password({
            "email": data.email,
            "password": data.password,
        })
    except Exception:
        raise HTTPException(status_code=401, detail="Nieprawidłowe dane logowania")

    if not auth_response.session:
        raise HTTPException(status_code=401, detail="Nieprawidłowe dane logowania")

    return TokenResponse(
        access_token=auth_response.session.access_token,
        refresh_token=auth_response.session.refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest):
    db = get_supabase()

    try:
        auth_response = db.auth.refresh_session(data.refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Nieprawidłowy refresh token")

    if not auth_response.session:
        raise HTTPException(status_code=401, detail="Nie można odświeżyć sesji")

    return TokenResponse(
        access_token=auth_response.session.access_token,
        refresh_token=auth_response.session.refresh_token,
    )


@router.post("/logout")
def logout(current_user: dict = Depends(get_current_user)):
    db = get_supabase()
    try:
        db.auth.sign_out()
    except Exception:
        pass
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return UserResponse(**current_user)


@router.patch("/me", response_model=UserResponse)
def update_me(data: UserUpdate, current_user: dict = Depends(get_current_user)):
    db = get_supabase()
    updates = data.model_dump(exclude_none=True)
    if updates:
        db.table("profiles").update(updates).eq("id", current_user["id"]).execute()

    # Zwróć zaktualizowane dane
    profile = db.table("profiles").select("*").eq("id", current_user["id"]).execute()
    profile_data = profile.data[0] if profile.data else {}
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        risk_profile=profile_data.get("risk_profile", "medium"),
        budget_pln=profile_data.get("budget_pln", 0),
        created_at=current_user["created_at"],
    )
