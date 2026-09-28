from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import auth, chat, travel
from app.core.config import settings
from app.core.exceptions import (
    global_exception_handler,
    sqlalchemy_exception_handler,
    validation_exception_handler,
)
from app.core.logging import setup_logging
from app.db import models  # noqa: F401  确保模型注册到 Base
from app.db.base import Base
from app.db.schema_sync import sync_schema
from app.db.session import engine
from app.rag.embedding import get_embedding_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    Base.metadata.create_all(bind=engine)
    # create_all 只建缺的表、不给已存在的表加列，老库缺的列在这里补（幂等，稳态只查一次表结构）。
    # 放在预热之前：表结构有问题要立刻炸，别等 15 秒加载完 2.3GB 模型才发现
    sync_schema(engine)
    # 预热嵌入模型（bge-m3 约 2.3GB，加载要十几秒）：放到启动时做，
    # 否则第一次检索会让用户干等，也避免它阻塞事件循环
    try:
        await anyio.to_thread.run_sync(get_embedding_model)
        print("[Startup] 嵌入模型预热完成")
    except Exception as exc:
        print(f"[Startup] 嵌入模型预热失败，首次检索会变慢：{type(exc).__name__}: {exc}")
    yield


app = FastAPI(
    title="旅行计划智能助手 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(travel.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
