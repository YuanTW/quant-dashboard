"""
database.py — 資料庫操作模組（懶初始化版本）
engine 在第一次呼叫時才建立，避免 import 時就崩潰
"""
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# ── ORM 基礎類別 ─────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


class StrategyResult(Base):
    __tablename__ = "strategy_results"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id    = Column(String(100), nullable=False, index=True)
    strategy_name  = Column(String(200), nullable=False)
    recommendation = Column(Text,        nullable=True)
    signal         = Column(String(20),  nullable=True)
    details        = Column(Text,        nullable=True)
    chart_path     = Column(String(500), nullable=True)
    status         = Column(String(20),  nullable=False, default="pending")
    error_message  = Column(Text,        nullable=True)
    updated_at     = Column(DateTime,    nullable=True)
    created_at     = Column(DateTime,    default=datetime.utcnow)


# ── 懶初始化：第一次呼叫才建立 engine ─────────────────────────────────────────
_engine = None
_SessionLocal = None


def _get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = os.getenv("DATABASE_URL", "sqlite:///quant_dashboard.db")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        kwargs = {"pool_pre_ping": True} if url.startswith("postgresql") else {}
        _engine = create_engine(url, **kwargs)
        _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    return _engine


def _get_session():
    _get_engine()
    return _SessionLocal()


def init_db():
    engine = _get_engine()
    Base.metadata.create_all(engine)


# ── CRUD ─────────────────────────────────────────────────────────────────────
def get_latest_result(strategy_id: str) -> Optional[StrategyResult]:
    try:
        with _get_session() as db:
            return (
                db.query(StrategyResult)
                .filter(StrategyResult.strategy_id == strategy_id)
                .order_by(StrategyResult.updated_at.desc())
                .first()
            )
    except Exception:
        return None


def get_all_latest_results():
    try:
        with _get_session() as db:
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
            db.expunge_all()
            return rows
    except Exception:
        return []


def upsert_running(strategy_id: str, strategy_name: str) -> int:
    with _get_session() as db:
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


def save_result(row_id: int, recommendation: str, signal: str,
                chart_path: Optional[str], details: Optional[str] = None):
    with _get_session() as db:
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
    with _get_session() as db:
        row = db.get(StrategyResult, row_id)
        if row:
            row.status        = "error"
            row.error_message = error_message
            row.updated_at    = datetime.utcnow()
            db.commit()


def get_result_by_id(row_id: int) -> Optional[StrategyResult]:
    with _get_session() as db:
        row = db.get(StrategyResult, row_id)
        if row:
            db.expunge(row)
        return row
