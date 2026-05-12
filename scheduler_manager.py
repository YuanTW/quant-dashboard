"""
scheduler_manager.py — 排程管理器
使用 APScheduler 在雲端按設定時間自動執行各策略並推播 Telegram

排程設定在 strategies_config.json 的 "schedule" 欄位，使用 Cron 格式：
  "0 8 * * 1-5"   → 週一到週五 08:00
  "30 13 * * 5"   → 每週五 13:30
  "0 */4 * * *"   → 每 4 小時整點
  "0 8,13 * * 1-5"→ 週一到週五 08:00 和 13:00

此模組設計為「只啟動一次的單例」，在 app.py 中用 threading 掛載。
"""
import json
import logging
import os
import threading
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

import config
import runner
import telegram_notifier as tg

logger = logging.getLogger(__name__)

# ── 單例 ──────────────────────────────────────────────────────────────────────
_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    with _lock:
        if _scheduler is None:
            tz = pytz.timezone(config.TIMEZONE)
            _scheduler = BackgroundScheduler(timezone=tz)
        return _scheduler


# ── 讀取策略設定 ────────────────────────────────────────────────────────────────
def load_strategies_config() -> list[dict]:
    cfg_path = Path(config.BASE_DIR) / "strategies_config.json"
    if not cfg_path.exists():
        logger.warning("找不到 strategies_config.json，排程器無策略可執行")
        return []
    with open(cfg_path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("strategies", [])


# ── 排程任務執行函式 ──────────────────────────────────────────────────────────────
def _scheduled_job(strategy: dict):
    """排程器觸發時呼叫此函式"""
    sid   = strategy["id"]
    name  = strategy["name"]
    script = os.path.join(config.BASE_DIR, strategy["script"])

    logger.info("排程觸發：%s", name)
    success, recommendation, chart_path = runner.run_strategy_sync(
        strategy_id   = sid,
        strategy_name = name,
        script_path   = script,
    )

    if success:
        tg.notify_strategy_result(
            strategy_name  = name,
            recommendation = recommendation,
            signal         = _parse_signal(recommendation),
            chart_path     = chart_path,
        )
    else:
        tg.notify_error(name, recommendation)


def _parse_signal(recommendation: str) -> str:
    """從推薦文字中猜測信號方向（可依需求調整）"""
    rec = recommendation.upper()
    if any(k in rec for k in ("做多", "買入", "BUY", "LONG", "多")):
        return "BUY"
    if any(k in rec for k in ("做空", "賣出", "SELL", "SHORT", "空")):
        return "SELL"
    return "HOLD"


# ── 啟動排程 ───────────────────────────────────────────────────────────────────
def start():
    """讀取設定並啟動所有排程任務"""
    sched = get_scheduler()
    if sched.running:
        logger.info("排程器已在執行中，略過重複啟動")
        return

    strategies = load_strategies_config()
    tz = pytz.timezone(config.TIMEZONE)

    for s in strategies:
        if not s.get("enabled", True):
            continue
        schedule = s.get("schedule", "")
        if not schedule:
            continue
        try:
            parts = schedule.strip().split()
            if len(parts) != 5:
                raise ValueError(f"Cron 格式不正確：{schedule}")

            minute, hour, day, month, day_of_week = parts
            trigger = CronTrigger(
                minute      = minute,
                hour        = hour,
                day         = day,
                month       = month,
                day_of_week = day_of_week,
                timezone    = tz,
            )
            sched.add_job(
                func     = _scheduled_job,
                trigger  = trigger,
                args     = [s],
                id       = f"strategy_{s['id']}",
                name     = s["name"],
                replace_existing = True,
            )
            logger.info("已加入排程：%s → %s", s["name"], schedule)
        except Exception as exc:
            logger.error("排程設定失敗 [%s]：%s", s["id"], exc)

    sched.start()
    logger.info("排程器已啟動，共 %d 個任務", len(sched.get_jobs()))


def list_jobs() -> list[dict]:
    """回傳目前所有排程任務的摘要"""
    sched = get_scheduler()
    if not sched.running:
        return []
    jobs = []
    for job in sched.get_jobs():
        jobs.append({
            "id":       job.id,
            "name":     job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else "—",
        })
    return jobs
