"""
database.py — 資料庫操作模組
支援 SQLite（本地開發）與 PostgreSQL（Railway 雲端）
策略每次執行結果都會寫入，保留歷史紀錄
"""
import json
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, DateTime, Integer, String, Text,
    create_engine, text
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

import config


# ── ORM 基礎類別 ─────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── 策略結果表 ────────────────────────────────────────────────────────────────
class StrategyResult(Base):
    __tablename__ = "strategy_results"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id    = Column(String(100), nullable=False, index=True)   # 策略唯一識別碼
    strategy_name  = Column(String(200), nullable=False)               # 顯示名稱
    recommendation = Column(Text,        nullable=True)                # 推薦方向文字
    signal         = Column(String(20),  nullable=True)                # BUY / SELL / HOLD
    details        = Column(Text,        nullable=True)                # 詳細說明（選填）
    chart_path     = Column(String(500), nullable=True)                # 損益圖路徑
    status         = Column(String(20),  nullable=False, default="pending")
    #   pending / running / success / error
    error_message  = Column(Text,        nullable=True)
    updated_at     = Column(DateTime,    nullable=True)
    created_at     = Column(DateTime,    default=datetime.utcnow)


# ── 引擎 & Session ───────────────────────────────────────────────────────────
def _make_engine():
    url = config.DATABASE_URL
    # Railway 的 PostgreSQL URL 有時以 postgres:// 開頭，SQLAlchemy 需要 postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    kwargs = {}
    if url.startswith("postgresql"):
        kwargs["pool_pre_ping"] = True
    return create_engine(url, **kwargs)


_engine = _make_engine()
SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def init_db():
    """建立所有資料表（若不存在）"""
    Base.metadata.create_all(_engine)


# ── CRUD ─────────────────────────────────────────────────────────────────────
def get_latest_result(strategy_id: str) -> Optional[StrategyResult]:
    """取得指定策略的最新一筆結果"""
    with SessionLocal() as db:
        return (
            db.query(StrategyResult)
            .filter(StrategyResult.strategy_id == strategy_id)
            .order_by(StrategyResult.updated_at.desc())
            .first()
        )


def get_all_latest_results() -> list[StrategyResult]:
    """取得每個策略 ID 最新一筆結果（用於儀表板主頁）"""
    with SessionLocal() as db:
        # 子查詢找出每個 strategy_id 最大 updated_at
        subq = (
            db.query(
                StrategyResult.strategy_id,
                StrategyResult.updated_at.label("max_updated"),
            )
            .group_by(StrategyResult.strategy_id)
            .subquery()
        )
        rows = (
            db.query(StrategyResult)
            .join(
                subq,
                (StrategyResult.strategy_id == subq.c.strategy_id)
                & (StrategyResult.updated_at == subq.c.max_updated),
            )
            .all()
        )
        # detach from session so caller can use outside context
        db.expunge_all()
        return rows


def upsert_running(strategy_id: str, strategy_name: str) -> int:
    """把策略狀態設為 running，回傳新 row 的 id"""
    with SessionLocal() as db:
        row = StrategyResult(
            strategy_id   = strategy_id,
            strategy_name = strategy_name,
            status        = "running",
            updated_at    = datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def save_result(
    row_id: int,
    recommendation: str,
    signal: str,
    chart_path: Optional[str],
    details: Optional[str] = None,
):
    """儲存策略執行成功結果"""
    with SessionLocal() as db:
        row = db.get(StrategyResult, row_id)
        if row:
            row.recommendation = recommendation
            row.signal         = signal
            row.chart_path     = chart_path
            row.details        = details
            row.status         = "success"
            row.updated_at     = datetime.utcnow()
            db.commit()


def save_error(row_id: int, error_message: str):
    """儲存策略執行失敗資訊"""
    with SessionLocal() as db:
        row = db.get(StrategyResult, row_id)
        if row:
            row.status        = "error"
            row.error_message = error_message
            row.updated_at    = datetime.utcnow()
            db.commit()


def get_result_by_id(row_id: int) -> Optional[StrategyResult]:
    with SessionLocal() as db:
        row = db.get(StrategyResult, row_id)
        if row:
            db.expunge(row)
        return row
