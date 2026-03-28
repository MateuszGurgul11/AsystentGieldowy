from supabase import create_client, Client
from config import get_settings
from functools import lru_cache


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError("Brak SUPABASE_URL lub SUPABASE_KEY w .env")
    return create_client(settings.supabase_url, settings.supabase_key)
