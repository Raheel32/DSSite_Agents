"""App entry point. Run with:  uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine, SessionLocal
from .routers import fraud
from .seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)   # create tables
    with SessionLocal() as db:
        seed_if_empty(db)                   # add sample data
    yield


app = FastAPI(title="AI Agents Service", version="0.1.0", lifespan=lifespan)

# CORS lets ANY website (WordPress, plain HTML...) call this API from the browser.
# Tighten allow_origins to your real domains before going live.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

app.include_router(fraud.router)


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}

@app.get("/", tags=["System"])
def root():
    return {
        "message": "AI Agents Service is running",
        "docs": "/docs",
        "agents": ["/fraud/check"],
    }
