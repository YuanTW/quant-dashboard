"""
app.py — 量化交易儀表板主應用
執行方式：streamlit run app.py
"""
import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytz
import streamlit as st

# ── 基本設定 ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="量化交易儀表板",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS 自訂樣式 ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, [class*="css"] { font-family: "PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif; }
.dash-header {
    background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    border-radius: 12px;
    padding: 20px 28px;
    margin-bottom: 24px;
    color: white;
}
.dash-header h1 { margin: 0; font-size: 1.8rem; letter-spacing: 2px; }
.dash-header p  { margin: 4px 0 0; opacity: .65; font-size: .9rem; }
.rec-badge {
    display: inline-block;
    padding: 5px 14px;
    border-radius: 20px;
    font-size: 1.1rem;
    font-weight: 700;
    margin: 8px 0;
}
.rec-buy  { background: #0d3d2e; color: #4ade80; border: 1px solid #16a34a; }
.rec-sell { background: #3d0d0d; color: #f87171; border: 1px solid #dc2626; }
.rec-hold { background: #3d3400; color: #fbbf24; border: 1px solid #d97706; }
.rec-none { background: #2a2a2a; color: #9ca3af; border: 1px solid #4b5563; }
.update-time { font-size: .78rem; color: #6b7280; margin: 2px 0 10px; }
</style>
""", unsafe_allow_html=True)


# ── 安全初始化（每個模組分開 try/except，避免一個錯誤讓整個 app 掛掉）──────────────
@st.cache_resource
def _init_db():
    try:
        import database as db
        db.init_db()
        return db
    except Exception as e:
        logger.error("資料庫初始化失敗：%s", e)
        return None


@st.cache_resource
def _init_scheduler():
    try:
        import scheduler_manager as sched
        sched.start()
        return sched
    except Exception as e:
        logger.warning("排程器啟動失敗（非致命錯誤）：%s", e)
        return None


db_module    = _init_db()
sched_module = _init_scheduler()


# ── 讀取策略設定 ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_strategies() -> list:
    try:
        cfg_path = Path(__file__).parent / "strategies_config.json"
        if not cfg_path.exists():
            return []
        with open(cfg_path, encoding="utf-8") as f:
            return json.load(f).get("strategies", [])
    except Exception as e:
        logger.error("讀取策略設定失敗：%s", e)
        return []


def get_tz_now() -> str:
    try:
        tz  = pytz.timezone("Asia/Taipei")
        now = datetime.now(tz)
        return now.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S (UTC)")


def signal_css(signal) -> str:
    if not signal:
        return "rec-none"
    s = signal.upper()
    if s in ("BUY", "LONG"):   return "rec-buy"
    if s in ("SELL", "SHORT"): return "rec-sell"
    if s == "HOLD":            return "rec-hold"
    return "rec-none"


def parse_signal_from_rec(rec: str) -> str:
    r = rec.upper()
    if any(k in r for k in ("做多","買入","BUY","LONG","多")): return "BUY"
    if any(k in r for k in ("做空","賣出","SELL","SHORT","空")): return "SELL"
    return "HOLD"


def fmt_time(dt) -> str:
    if dt is None:
        return "尚未執行"
    try:
        tz  = pytz.timezone("Asia/Taipei")
        loc = dt.replace(tzinfo=pytz.utc).astimezone(tz)
        return loc.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(dt)


def trigger_strategy(strategy: dict):
    if db_module is None:
        st.error("資料庫未初始化，無法執行策略")
        return
    try:
        import runner
        sid    = strategy["id"]
        script = str(Path(__file__).parent / strategy["script"])
        st.session_state[f"running_{sid}"] = True

        def _on_complete(strategy_id, success, msg):
            st.session_state[f"running_{strategy_id}"] = False

        runner.run_strategy(
            strategy_id   = sid,
            strategy_name = strategy["name"],
            script_path   = script,
            on_complete   = _on_complete,
        )
    except Exception as e:
        st.error(f"執行策略失敗：{e}")


# ── 頁首 ───────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="dash-header">
  <h1>📊 量化交易儀表板</h1>
  <p>Quantitative Trading Monitor &nbsp;·&nbsp; {get_tz_now()}</p>
</div>
""", unsafe_allow_html=True)


# ── 頂部操作列 ─────────────────────────────────────────────────────────────────
strategies = load_strategies()
col_l, col_r = st.columns([6, 2])

with col_r:
    if st.button("🔄 更新全部策略", use_container_width=True, type="primary"):
        for s in strategies:
            if s.get("enabled", True):
                trigger_strategy(s)
        st.toast("已觸發所有策略更新，請稍候…")
        time.sleep(1)
        st.rerun()

with col_l:
    if db_module is None:
        st.warning("⚠️ 資料庫初始化失敗，部分功能無法使用")
    if sched_module is None:
        st.caption("⚠️ 排程器未啟動（Telegram 定時推播暫停）")


# ── 策略卡片區 ─────────────────────────────────────────────────────────────────
if not strategies:
    st.info("尚未設定任何策略。請編輯 `strategies_config.json` 新增策略，並重新部署。")
    st.stop()

cols_per_row = 3
rows = [strategies[i:i+cols_per_row] for i in range(0, len(strategies), cols_per_row)]

for row in rows:
    cols = st.columns(len(row))
    for col, strategy in zip(cols, row):
        sid    = strategy["id"]
        sname  = strategy["name"]
        is_run = st.session_state.get(f"running_{sid}", False)
        latest = db_module.get_latest_result(sid) if db_module else None

        with col:
            with st.container(border=True):
                st.markdown(f"### {sname}")

                if is_run:
                    st.markdown("🔵 **執行中…**")
                elif latest:
                    status_text = {"success":"🟢 成功","error":"🔴 錯誤","running":"🔵 執行中","pending":"⚪ 等待中"}.get(latest.status,"⚪")
                    st.markdown(status_text)
                    st.markdown(f'<div class="update-time">🕐 更新：{fmt_time(latest.updated_at)}</div>', unsafe_allow_html=True)

                # 推薦方向
                if latest and latest.status == "success":
                    rec    = latest.recommendation or "—"
                    signal = latest.signal or parse_signal_from_rec(rec)
                    css    = signal_css(signal)
                    st.markdown(f'<div class="rec-badge {css}">{rec}</div>', unsafe_allow_html=True)
                    if latest.details:
                        with st.expander("詳細說明"):
                            st.write(latest.details)
                elif latest and latest.status == "error":
                    st.error(f"執行錯誤：{latest.error_message}")
                elif latest and latest.status == "running":
                    st.info("策略執行中，請稍候…")
                else:
                    st.markdown('<div class="rec-badge rec-none">尚無資料</div>', unsafe_allow_html=True)

                # 損益圖
                chart = latest.chart_path if latest else None
                if chart and Path(chart).exists():
                    try:
                        from PIL import Image
                        img = Image.open(chart)
                        st.image(img, use_container_width=True)
                    except Exception:
                        st.caption("圖片載入失敗")
                else:
                    st.markdown(
                        "<div style='height:120px;display:flex;align-items:center;"
                        "justify-content:center;color:#6b7280;font-size:.85rem;"
                        "border:1px dashed #374151;border-radius:8px;margin:8px 0'>"
                        "📈 執行後顯示損益圖</div>",
                        unsafe_allow_html=True
                    )

                # 更新按鈕
                btn_label = "⏳ 執行中..." if is_run else "🔄 更新此策略"
                if st.button(btn_label, key=f"btn_{sid}", disabled=is_run, use_container_width=True):
                    trigger_strategy(strategy)
                    st.toast(f"已觸發「{sname}」更新")
                    time.sleep(0.5)
                    st.rerun()


# ── 排程狀態 ───────────────────────────────────────────────────────────────────
st.divider()
with st.expander("⏰ 排程任務狀態", expanded=False):
    if sched_module:
        jobs = sched_module.list_jobs()
        if jobs:
            for job in jobs:
                st.caption(f"**{job['name']}** — 下次執行：{job['next_run']}")
        else:
            st.caption("排程器已啟動，尚無任務")
    else:
        st.caption("排程器未啟動（Streamlit Cloud 不支援永久背景執行緒，請改用 Railway 以啟用排程）")

with st.expander("📱 Telegram 設定說明", expanded=False):
    st.markdown("""
1. 在 Telegram 搜尋 `@BotFather` → `/newbot` → 取得 **BOT_TOKEN**
2. 對 Bot 發任意訊息，開啟 `https://api.telegram.org/bot你的TOKEN/getUpdates`，找到 `chat.id`
3. 在 Streamlit Cloud → **Settings → Secrets** 填入：
```toml
TELEGRAM_BOT_TOKEN = "你的 Token"
TELEGRAM_CHAT_ID = "你的 Chat ID"
```
""")

# ── 若有策略執行中，每 5 秒自動刷新 ─────────────────────────────────────────────
if any(st.session_state.get(f"running_{s['id']}", False) for s in strategies):
    time.sleep(5)
    st.rerun()

