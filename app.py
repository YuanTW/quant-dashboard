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
from PIL import Image

import config
import database as db
import runner
import scheduler_manager as sched
import telegram_notifier as tg

# ── 基本設定 ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title = config.DASHBOARD_TITLE,
    page_icon  = "📊",
    layout     = "wide",
    initial_sidebar_state = "collapsed",
)

# ── CSS 自訂樣式 ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* 全域字體 */
html, body, [class*="css"] { font-family: "PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif; }

/* 頁首 */
.dash-header {
    background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    border-radius: 12px;
    padding: 20px 28px;
    margin-bottom: 24px;
    color: white;
}
.dash-header h1 { margin: 0; font-size: 1.8rem; letter-spacing: 2px; }
.dash-header p  { margin: 4px 0 0; opacity: .65; font-size: .9rem; }

/* 策略卡片 */
.strategy-card {
    background: #1e2130;
    border-radius: 12px;
    padding: 18px 20px;
    border: 1px solid #2d3250;
    height: 100%;
}
.strategy-card h3 { margin: 0 0 4px; font-size: 1rem; color: #c0c8e8; }

/* 推薦標籤 */
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

/* 狀態點 */
.dot-running { color: #60a5fa; animation: blink 1s infinite; }
.dot-success { color: #4ade80; }
.dot-error   { color: #f87171; }
.dot-pending { color: #9ca3af; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }

/* 更新時間 */
.update-time { font-size: .78rem; color: #6b7280; margin: 2px 0 10px; }

/* 排程表格 */
.sched-row { font-size: .82rem; border-bottom: 1px solid #2d3250; padding: 6px 0; }
</style>
""", unsafe_allow_html=True)


# ── 初始化（只在 process 啟動時執行一次）──────────────────────────────────────────
@st.cache_resource
def _init():
    db.init_db()
    sched.start()
    return True

_init()


# ── 讀取策略設定 ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_strategies() -> list[dict]:
    cfg_path = Path(config.BASE_DIR) / "strategies_config.json"
    if not cfg_path.exists():
        return []
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f).get("strategies", [])


def get_tz_now() -> str:
    tz  = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S")


# ── 信號 → 樣式 ────────────────────────────────────────────────────────────────
def signal_css(signal: Optional[str]) -> str:
    if not signal:
        return "rec-none"
    s = signal.upper()
    if s in ("BUY", "LONG"):
        return "rec-buy"
    if s in ("SELL", "SHORT"):
        return "rec-sell"
    if s == "HOLD":
        return "rec-hold"
    return "rec-none"


def parse_signal_from_rec(rec: str) -> str:
    r = rec.upper()
    if any(k in r for k in ("做多","買入","BUY","LONG","多")):
        return "BUY"
    if any(k in r for k in ("做空","賣出","SELL","SHORT","空")):
        return "SELL"
    return "HOLD"


def status_dot(status: Optional[str]) -> str:
    mapping = {
        "running": '<span class="dot-running">⬤ 執行中</span>',
        "success": '<span class="dot-success">⬤ 成功</span>',
        "error":   '<span class="dot-error">⬤ 錯誤</span>',
        "pending": '<span class="dot-pending">⬤ 等待中</span>',
    }
    return mapping.get(status or "pending", mapping["pending"])


def fmt_time(dt: Optional[datetime]) -> str:
    if dt is None:
        return "尚未執行"
    tz  = pytz.timezone(config.TIMEZONE)
    loc = dt.replace(tzinfo=pytz.utc).astimezone(tz)
    return loc.strftime("%Y-%m-%d %H:%M:%S")


# ── 執行策略並更新 session_state ───────────────────────────────────────────────
def trigger_strategy(strategy: dict):
    sid = strategy["id"]
    st.session_state[f"running_{sid}"] = True
    script = os.path.join(config.BASE_DIR, strategy["script"])

    def _on_complete(strategy_id, success, msg):
        st.session_state[f"running_{strategy_id}"] = False
        if success and tg.is_configured():
            latest = db.get_latest_result(strategy_id)
            if latest:
                tg.notify_strategy_result(
                    strategy_name  = strategy["name"],
                    recommendation = latest.recommendation or "",
                    signal         = latest.signal or "",
                    chart_path     = latest.chart_path,
                )

    runner.run_strategy(
        strategy_id   = sid,
        strategy_name = strategy["name"],
        script_path   = script,
        on_complete   = _on_complete,
    )


def trigger_all(strategies: list[dict]):
    for s in strategies:
        if s.get("enabled", True):
            trigger_strategy(s)


# ── 頁首 ───────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="dash-header">
  <h1>📊 {config.DASHBOARD_TITLE}</h1>
  <p>{config.DASHBOARD_SUBTITLE} &nbsp;·&nbsp; {get_tz_now()}</p>
</div>
""", unsafe_allow_html=True)


# ── 頂部操作列 ─────────────────────────────────────────────────────────────────
strategies = load_strategies()
top_l, top_r = st.columns([6, 2])

with top_r:
    if st.button("🔄 更新全部策略", use_container_width=True, type="primary"):
        trigger_all(strategies)
        st.toast("已觸發所有策略更新，請稍候…")
        time.sleep(1)
        st.rerun()

with top_l:
    tg_status = "✅ Telegram 已設定" if tg.is_configured() else "⚠️ Telegram 未設定（見設定頁）"
    st.caption(tg_status)


# ── 策略卡片區 ─────────────────────────────────────────────────────────────────
if not strategies:
    st.warning("找不到任何策略設定，請編輯 `strategies_config.json` 新增策略。")
    st.stop()

# 每列最多 3 個卡片
cols_per_row = 3
rows = [strategies[i:i+cols_per_row] for i in range(0, len(strategies), cols_per_row)]

for row in rows:
    cols = st.columns(len(row))
    for col, strategy in zip(cols, row):
        sid     = strategy["id"]
        sname   = strategy["name"]
        is_run  = st.session_state.get(f"running_{sid}", False)
        latest  = db.get_latest_result(sid)

        with col:
            with st.container(border=True):
                # ── 標題列 ──────────────────────────────────────────────────
                st.markdown(f"### {sname}")
                if is_run:
                    st.markdown(status_dot("running"), unsafe_allow_html=True)
                elif latest:
                    st.markdown(status_dot(latest.status), unsafe_allow_html=True)
                    st.markdown(
                        f'<div class="update-time">🕐 更新：{fmt_time(latest.updated_at)}</div>',
                        unsafe_allow_html=True
                    )

                # ── 推薦方向 ─────────────────────────────────────────────────
                if latest and latest.status == "success":
                    rec    = latest.recommendation or "—"
                    signal = latest.signal or parse_signal_from_rec(rec)
                    css    = signal_css(signal)
                    st.markdown(
                        f'<div class="rec-badge {css}">{rec}</div>',
                        unsafe_allow_html=True
                    )
                    if latest.details:
                        with st.expander("詳細說明"):
                            st.write(latest.details)
                elif latest and latest.status == "error":
                    st.error(f"執行錯誤：{latest.error_message}")
                elif latest and latest.status == "running":
                    st.info("策略執行中，請稍候…")
                else:
                    st.markdown(
                        '<div class="rec-badge rec-none">尚無資料</div>',
                        unsafe_allow_html=True
                    )

                # ── 損益圖 ───────────────────────────────────────────────────
                chart = latest.chart_path if latest else None
                if chart and Path(chart).exists():
                    try:
                        img = Image.open(chart)
                        st.image(img, use_container_width=True)
                    except Exception:
                        st.caption("圖片載入失敗")
                else:
                    st.markdown(
                        "<div style='height:140px;display:flex;align-items:center;"
                        "justify-content:center;color:#4b5563;font-size:.85rem;"
                        "border:1px dashed #374151;border-radius:8px;margin:8px 0'>"
                        "📈 損益圖將在首次執行後顯示</div>",
                        unsafe_allow_html=True
                    )

                # ── 單一更新按鈕 ─────────────────────────────────────────────
                btn_label = "⏳ 執行中..." if is_run else "🔄 更新此策略"
                if st.button(btn_label, key=f"btn_{sid}", disabled=is_run,
                             use_container_width=True):
                    trigger_strategy(strategy)
                    st.toast(f"已觸發「{sname}」更新")
                    time.sleep(0.5)
                    st.rerun()


# ── 排程狀態區 ─────────────────────────────────────────────────────────────────
st.divider()
with st.expander("⏰ 排程任務狀態", expanded=False):
    jobs = sched.list_jobs()
    if jobs:
        header_cols = st.columns([2, 3, 3])
        header_cols[0].markdown("**策略 ID**")
        header_cols[1].markdown("**策略名稱**")
        header_cols[2].markdown("**下次執行時間**")
        for job in jobs:
            c1, c2, c3 = st.columns([2, 3, 3])
            c1.caption(job["id"])
            c2.caption(job["name"])
            c3.caption(job["next_run"])
    else:
        st.caption("排程器尚無任務或尚未啟動")


# ── Telegram 設定提示 ──────────────────────────────────────────────────────────
with st.expander("📱 Telegram 設定說明", expanded=False):
    st.markdown("""
**取得 Bot Token：**
1. 在 Telegram 搜尋 `@BotFather`
2. 發送 `/newbot`，依指示建立 Bot
3. 取得 `BOT_TOKEN`

**取得你的 Chat ID：**
1. 對你的 Bot 隨便傳一則訊息
2. 在瀏覽器開啟 `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
3. 從 JSON 回傳中找 `"id"` 欄位即是你的 Chat ID

**設定環境變數（.env 或 Railway 環境變數）：**
```
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNopQRstuVwXyz
TELEGRAM_CHAT_ID=987654321
```
""")


# ── 自動刷新（每 30 秒）────────────────────────────────────────────────────────
# 若有任何策略在 running 狀態，每 5 秒自動刷新
any_running = any(
    st.session_state.get(f"running_{s['id']}", False)
    for s in strategies
)
if any_running:
    time.sleep(5)
    st.rerun()
