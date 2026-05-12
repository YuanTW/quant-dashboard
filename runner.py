"""
runner.py — 策略執行引擎
負責在背景執行你的 Python 策略腳本，並將結果存入資料庫

【策略腳本的輸出約定】
你的腳本需要把結果存到 STRATEGY_OUTPUT_DIR 環境變數指定的資料夾：
  - recommendation.txt  → 推薦方向文字（例如：做多、做空、觀望）
  - chart.png           → 累積損益圖
  - result.json         → （選填）{ "signal": "BUY", "details": "..." }

Runner 執行前會自動建立這個資料夾並設好環境變數。
詳細範例請見 strategies/strategy_template.py
"""
import json
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import config
import database as db

logger = logging.getLogger(__name__)


# ── 執行單一策略（在子執行緒中非同步執行）────────────────────────────────────────
def run_strategy(
    strategy_id: str,
    strategy_name: str,
    script_path: str,
    on_complete: Optional[Callable[[str, bool, str], None]] = None,
):
    """
    在背景執行緒中執行策略腳本。

    Parameters
    ----------
    strategy_id   : 策略唯一識別碼（英文，用於資料庫 & 輸出目錄）
    strategy_name : 儀表板顯示名稱
    script_path   : 腳本的絕對或相對路徑
    on_complete   : 完成後的 callback(strategy_id, success, message)
    """
    thread = threading.Thread(
        target=_execute,
        args=(strategy_id, strategy_name, script_path, on_complete),
        daemon=True,
    )
    thread.start()
    return thread


def run_all_strategies(strategies: list[dict], on_complete=None):
    """同時觸發所有策略（各自在獨立執行緒）"""
    threads = []
    for s in strategies:
        if not s.get("enabled", True):
            continue
        t = run_strategy(
            strategy_id   = s["id"],
            strategy_name = s["name"],
            script_path   = s["script"],
            on_complete   = on_complete,
        )
        threads.append(t)
    return threads


# ── 實際執行邏輯（在子執行緒中跑）────────────────────────────────────────────────
def _execute(
    strategy_id: str,
    strategy_name: str,
    script_path: str,
    on_complete: Optional[Callable],
):
    # 1. 建立輸出目錄
    output_dir = Path(config.OUTPUTS_DIR) / strategy_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2. 在 DB 寫入 running 狀態
    row_id = db.upsert_running(strategy_id, strategy_name)

    # 3. 準備環境變數
    env = os.environ.copy()
    env["STRATEGY_OUTPUT_DIR"] = str(output_dir)
    env["STRATEGY_ID"]         = strategy_id

    script_abs = os.path.abspath(script_path)
    if not os.path.exists(script_abs):
        msg = f"找不到腳本：{script_abs}"
        db.save_error(row_id, msg)
        logger.error(msg)
        if on_complete:
            on_complete(strategy_id, False, msg)
        return

    # 4. 執行腳本
    try:
        result = subprocess.run(
            [sys.executable, script_abs],
            env=env,
            capture_output=True,
            text=True,
            timeout=300,   # 最多等 5 分鐘
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "腳本執行失敗")
    except subprocess.TimeoutExpired:
        db.save_error(row_id, "執行逾時（超過 5 分鐘）")
        if on_complete:
            on_complete(strategy_id, False, "執行逾時")
        return
    except Exception as exc:
        db.save_error(row_id, str(exc))
        logger.exception("策略執行例外：%s", strategy_id)
        if on_complete:
            on_complete(strategy_id, False, str(exc))
        return

    # 5. 讀取輸出
    recommendation = _read_text(output_dir / "recommendation.txt") or "（無推薦文字）"
    chart_path     = _find_chart(output_dir)
    signal, details = _read_json(output_dir / "result.json")

    # 6. 存入 DB
    db.save_result(
        row_id         = row_id,
        recommendation = recommendation,
        signal         = signal,
        chart_path     = str(chart_path) if chart_path else None,
        details        = details,
    )
    logger.info("策略完成：%s", strategy_id)
    if on_complete:
        on_complete(strategy_id, True, recommendation)


# ── 輔助函式 ──────────────────────────────────────────────────────────────────
def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _find_chart(directory: Path) -> Optional[Path]:
    """依優先順序尋找圖片：chart.png > chart.jpg > 任意第一個圖片"""
    for name in ("chart.png", "chart.jpg", "chart.jpeg"):
        p = directory / name
        if p.exists():
            return p
    for p in directory.iterdir():
        if p.suffix.lower() in (".png", ".jpg", ".jpeg"):
            return p
    return None


def _read_json(path: Path) -> tuple[str, Optional[str]]:
    """讀取 result.json，回傳 (signal, details)"""
    try:
        data    = json.loads(path.read_text(encoding="utf-8"))
        signal  = data.get("signal", "")
        details = data.get("details")
        return signal, details
    except Exception:
        return "", None


# ── 同步版本（給排程器呼叫，會等待執行完畢）──────────────────────────────────────
def run_strategy_sync(
    strategy_id: str,
    strategy_name: str,
    script_path: str,
) -> tuple[bool, str, Optional[str]]:
    """
    同步執行策略，等待完成後回傳。
    Returns: (success, recommendation, chart_path)
    """
    import time
    result_box = {}

    def _cb(sid, success, msg):
        result_box["success"] = success
        result_box["msg"]     = msg

    run_strategy(strategy_id, strategy_name, script_path, on_complete=_cb)

    # 等待執行緒完成（輪詢）
    for _ in range(360):      # 最多等 6 分鐘
        if result_box:
            break
        time.sleep(1)

    success = result_box.get("success", False)
    msg     = result_box.get("msg", "")

    # 取最新 chart_path
    latest = db.get_latest_result(strategy_id)
    chart  = latest.chart_path if latest else None
    return success, msg, chart
