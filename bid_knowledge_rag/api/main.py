"""FastAPI 应用入口"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from api.routes import knowledge, search

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting...")
    yield
    logger.info("Application shutting down...")


settings = get_settings()

app = FastAPI(
    title=settings.app.name,
    version=settings.app.version,
    description="投标知识库 RAG 系统 API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


# 注册路由
app.include_router(knowledge.router, prefix="/knowledge", tags=["知识管理"])
app.include_router(search.router, prefix="/search", tags=["检索服务"])


@app.get("/")
async def root():
    return {
        "name": settings.app.name,
        "version": settings.app.version,
        "status": "running",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/info")
async def get_info():
    return {
        "name": settings.app.name,
        "version": settings.app.version,
        "embedding_model": settings.embedding.model_name,
        "llm_model": settings.llm.model,
    }
