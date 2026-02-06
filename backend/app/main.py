"""Main FastAPI application."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api import agents, services, jobs, inbox, events, payments, deposits, withdrawals, negotiations
# quotes temporarily disabled (requires anthropic package for LLM negotiation - using P2P instead)

# Create FastAPI app
app = FastAPI(
    title="AgentMarket API",
    version="1.0.0",
    description="A marketplace where AI agents create fixed-price services and other agents directly purchase them"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(
    agents.router,
    prefix=f"{settings.API_V1_PREFIX}/agents",
    tags=["agents"]
)
app.include_router(
    services.router,
    prefix=f"{settings.API_V1_PREFIX}/services",
    tags=["services"]
)
app.include_router(
    jobs.router,
    prefix=f"{settings.API_V1_PREFIX}/jobs",
    tags=["jobs"]
)
app.include_router(
    inbox.router,
    prefix=f"{settings.API_V1_PREFIX}/inbox",
    tags=["inbox"]
)
app.include_router(
    events.router,
    prefix=f"{settings.API_V1_PREFIX}",
    tags=["events"]
)
app.include_router(
    payments.router,
    prefix=f"{settings.API_V1_PREFIX}/payments",
    tags=["payments"]
)
app.include_router(
    deposits.router,
    prefix=f"{settings.API_V1_PREFIX}",
    tags=["deposits"]
)
app.include_router(
    withdrawals.router,
    prefix=f"{settings.API_V1_PREFIX}",
    tags=["withdrawals"]
)
# LLM-based quotes disabled (using P2P negotiation instead)
# app.include_router(
#     quotes.router,
#     prefix=f"{settings.API_V1_PREFIX}",
#     tags=["quotes"]
# )
app.include_router(
    negotiations.router,
    prefix=f"{settings.API_V1_PREFIX}",
    tags=["negotiations"]
)


@app.on_event("startup")
async def startup():
    """Application startup tasks."""
    print(f"🚀 AgentMarket API starting...")
    print(f"📝 Environment: {settings.ENVIRONMENT}")
    print(f"📊 API Docs: http://localhost:8000/docs")


@app.on_event("shutdown")
async def shutdown():
    """Application shutdown tasks."""
    print("👋 AgentMarket API shutting down...")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "AgentMarket API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
    }


# Global exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Handle HTTP exceptions with consistent error format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )
