import asyncio
import logging
import sys
import os

# Dodaj katalog backend do PYTHONPATH
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import auth, portfolio, analysis, alerts, chat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Asystent Giełdowy API",
    description="Multi-agent investment assistant backend",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # W produkcji ogranicz do domeny frontendu
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routery
app.include_router(auth.router)
app.include_router(portfolio.router)
app.include_router(analysis.router)
app.include_router(alerts.router)
app.include_router(chat.router)


@app.on_event("startup")
async def startup():
    logger.info("Uruchamianie Asystenta Giełdowego v2.0...")

    # Uruchom background monitory
    from monitors.twitter_monitor import twitter_monitor
    from monitors.news_monitor import news_monitor
    from monitors.market_monitor import market_monitor

    asyncio.create_task(twitter_monitor())
    asyncio.create_task(news_monitor())
    asyncio.create_task(market_monitor())

    logger.info("Background monitory uruchomione")
    logger.info(f"API dostępne pod http://{settings.app_host}:{settings.app_port}/docs")


@app.get("/")
def root():
    return {
        "name": "Asystent Giełdowy API",
        "version": "2.0.0",
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health")
async def health():
    from llm.client import ollama_available
    ollama_ok = await ollama_available()
    return {
        "status": "ok",
        "ollama": "connected" if ollama_ok else "disconnected",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
        log_level="info",
    )
