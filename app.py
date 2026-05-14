"""
app.py — 量化交易儀表板
=======================
專業深色主題，每格策略卡含：
  • 投資建議徽章（做多/做空/觀望）
  • 核心績效指標（YTD、總報酬、夏普值、最大回撤）
  • Plotly 互動圖表，內建時間段選擇（3M / 6M / YTD / 1Y / ALL）
  • 個別策略刷新按鈕 + 全部刷新按鈕

新增策略：
  1. 在 strategies/ 資料夾新增一個 .py 檔，實作 run() → dict
  2. 在下方 STRATEGY_REGISTRY 加一行 dict
"""

import importlib
import os
import sys
import time
from datetime import datetime, date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytz
import streamlit as st

# ── 確保 strategies/ 可被 import ──────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

TW = pytz.timezone("Asia/Taipei")

# ══════════════════════════════════════════════════════════════════════════════
#  策略登錄表  ← 在這裡新增你的策略
# ══════════════════════════════════════════════════════════════════════════════
STRATEGY_REGISTRY = [
    {
        "id":     "demo_momentum",
        "name":   "動量策略 — 台灣50",
        "module": "strategies.demo_momentum",
    },
    {
        "id":     "demo_mean_revert",
        "name":   "均值回歸 — S&P500",
        "module": "strategies.demo_mean_revert",
    },
    # ── 新增你的策略 ──────────────────────────────────────────────────────────
    # {
    #     "id":     "my_strategy",
    #     "name":   "我的自訂策略",
    #     "module": "strategies.my_strategy",
    # },
]

# ══════════════════════════════════════════════════════════════════════════════
#  頁面設定
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="量化交易儀表板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════════════════════
#  CSS — 深色主題
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
/* ── 全域 ───────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stApp"] {
    background-color: #0d1117 !important;
    color: #e6edf3;
}
[data-testid="stSidebar"] {
    background: #161b22 !important;
    border-right: 1px solid #30363d;
}
/* 隱藏頂部工具列 */
#MainMenu, footer, header { visibility: hidden !important; }
.stDeployButton { display: none !important; }
div[data-testid="stToolbar"] { display: none !important; }

/* ── 標題區 ─────────────────────────────────────────── */
.dash-header {
    padding: 1.25rem 0 1rem 0;
    border-bottom: 1px solid #21262d;
    margin-bottom: 1.5rem;
}
.dash-title {
    font-size: 1.55rem;
    font-weight: 700;
    color: #e6edf3;
    letter-spacing: -0.3px;
    margin: 0;
}
.dash-subtitle {
    font-size: 0.8rem;
    color: #8b949e;
    margin: 3px 0 0 0;
}

/* ── 策略卡 ─────────────────────────────────────────── */
div[data-testid="stVerticalBlockBorderWrapper"] > div {
    background: #161b22 !important;
    border: 1px solid #21262d !important;
    border-radius: 12px !important;
    padding: 1rem 1.1rem !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div:hover {
    border-color: #1f6feb !important;
    transition: border-color 0.2s;
}

/* ── 訊號徽章 ───────────────────────────────────────── */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.4px;
}
.badge-long    { background: rgba(63,185,80,0.15);  color: #3fb950; border: 1px solid rgba(63,185,80,0.35); }
.badge-short   { background: rgba(248,81,73,0.15);  color: #f85149; border: 1px solid rgba(248,81,73,0.35); }
.badge-neutral { background: rgba(210,153,34,0.15); color: #d29922; border: 1px solid rgba(210,153,34,0.35); }

/* ── 指標方塊 ───────────────────────────────────────── */
.metric-box { text-align: center; padding: 4px 0 6px 0; }
.metric-val { font-size: 1.2rem; font-weight: 700; line-height: 1.3; }
.metric-lbl { font-size: 0.7rem; color: #8b949e; margin-top: 1px; }

/* ── 分隔線 ─────────────────────────────────────────── */
.divider { border-top: 1px solid #21262d; margin: 8px 0; }

/* ── 說明文字 ───────────────────────────────────────── */
.detail-text {
    font-size: 0.78rem;
    color: #8b949e;
    line-height: 1.55;
    margin-top: 4px;
}

/* ── 時間戳記 ───────────────────────────────────────── */
.timestamp { font-size: 0.72rem; color: #6e7681; }

/* ── 按鈕覆寫 ───────────────────────────────────────── */
button[kind="primary"] {
    background: #1f6feb !important;
    border: none !important;
    color: #fff !important;
    font-weight: 600 !important;
}
button[kind="secondary"] {
    background: #21262d !important;
    border: 1px solid #30363d !important;
    color: #c9d1d9 !important;
}

/* ── Plotly 圖表背景透明 ────────────────────────────── */
.js-plotly-plot .plotly { background: transparent !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  工具函式
# ══════════════════════════════════════════════════════════════════════════════

def _badge_html(signal: str, recommendation: str) -> str:
    cls = {"LONG": "badge-long", "SHORT": "badge-short"}.get(signal, "badge-neutral")
    return f'<span class="badge {cls}">{recommendation}</span>'


def _color(val: float) -> str:
    return "#3fb950" if val >= 0 else "#f85149"


def _fmt_pct(val: float, show_sign: bool = True) -> str:
    sign = "+" if val >= 0 and show_sign else ""
    return f"{sign}{val * 100:.2f}%"


def compute_metrics(returns: pd.Series) -> dict:
    if returns is None or len(returns) == 0:
        return {}
    cum = (1 + returns).cumprod() - 1
    total_ret = float(cum.iloc[-1])
    n_years = len(returns) / 252
    ann_ret = float((1 + total_ret) ** (1 / max(n_years, 0.01)) - 1)
    sharpe = float((returns.mean() / returns.std()) * np.sqrt(252)) if returns.std() > 0 else 0.0
    # Max drawdown
    wealth = (1 + returns).cumprod()
    peak = wealth.cummax()
    max_dd = float(((wealth - peak) / peak).min())
    # YTD
    ytd_start = pd.Timestamp(date.today().year, 1, 1)
    ytd = returns[returns.index >= ytd_start]
    ytd_ret = float((1 + ytd).prod() - 1) if len(ytd) > 0 else 0.0
    return {
        "total_ret": total_ret,
        "ann_ret":   ann_ret,
        "sharpe":    sharpe,
        "max_dd":    max_dd,
        "ytd_ret":   ytd_ret,
    }


def build_chart(returns: pd.Series, name: str) -> go.Figure:
    """Plotly 累積報酬圖，帶 rangeselector（3M/6M/YTD/1Y/ALL）。"""
    cum = (1 + returns).cumprod() - 1
    final = float(cum.iloc[-1]) if len(cum) else 0
    lc = "#3fb950" if final >= 0 else "#f85149"
    fc = "rgba(63,185,80,0.08)" if final >= 0 else "rgba(248,81,73,0.08)"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cum.index,
        y=(cum.values * 100).round(3),
        mode="lines",
        fill="tozeroy",
        fillcolor=fc,
        line=dict(color=lc, width=1.8),
        name="累積報酬",
        hovertemplate="<b>%{x|%Y/%m/%d}</b><br>累積報酬：%{y:.2f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dot",
                  line_color="rgba(139,148,158,0.25)", line_width=1)

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#8b949e", size=11),
        margin=dict(l=4, r=4, t=36, b=4),
        showlegend=False,
        height=230,
        xaxis=dict(
            showgrid=False,
            showline=False,
            zeroline=False,
            tickfont=dict(color="#6e7681", size=10),
            type="date",
            rangeselector=dict(
                buttons=[
                    dict(count=3,  label="3M",  step="month", stepmode="backward"),
                    dict(count=6,  label="6M",  step="month", stepmode="backward"),
                    dict(count=1,  label="YTD", step="year",  stepmode="todate"),
                    dict(count=1,  label="1Y",  step="year",  stepmode="backward"),
                    dict(step="all", label="ALL"),
                ],
                bgcolor="#0d1117",
                activecolor="#1f6feb",
                bordercolor="#30363d",
                borderwidth=1,
                font=dict(color="#c9d1d9", size=11),
                x=0,
                y=1.0,
                xanchor="left",
                yanchor="bottom",
            ),
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(33,38,45,0.8)",
            showline=False,
            zeroline=False,
            tickfont=dict(color="#6e7681", size=10),
            ticksuffix="%",
            side="right",
        ),
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  策略執行（快取）
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def run_strategy_cached(strategy_id: str, module_path: str, _ts: float) -> dict:
    """執行策略並快取結果；_ts 不同時強制重新執行。"""
    try:
        mod = importlib.import_module(module_path)
        importlib.reload(mod)
        result = mod.run()
        result["success"] = True
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
    result["updated_at"] = datetime.now(TW).strftime("%Y/%m/%d %H:%M")
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  Session State — 刷新時間戳記
# ══════════════════════════════════════════════════════════════════════════════
if "ts" not in st.session_state:
    st.session_state.ts = {}


def _get_ts(sid: str) -> float:
    return st.session_state.ts.get(sid, 0.0)


def _touch(sid: str):
    st.session_state.ts[sid] = time.time()


def _touch_all():
    t = time.time()
    for s in STRATEGY_REGISTRY:
        st.session_state.ts[s["id"]] = t


# ══════════════════════════════════════════════════════════════════════════════
#  儀表板標題
# ══════════════════════════════════════════════════════════════════════════════
hdr_l, hdr_r = st.columns([5, 1])
with hdr_l:
    st.markdown("""
    <div class="dash-header">
        <p class="dash-title">📈 量化交易儀表板</p>
        <p class="dash-subtitle">Quantitative Trading Dashboard · 即時策略監控</p>
    </div>
    """, unsafe_allow_html=True)
with hdr_r:
    st.markdown("<div style='padding-top:1.6rem'></div>", unsafe_allow_html=True)
    if st.button("🔄 全部刷新", type="primary", use_container_width=True):
        _touch_all()
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
#  策略卡片格線（每行 2 格）
# ══════════════════════════════════════════════════════════════════════════════
cols = st.columns(2, gap="medium")

for i, cfg in enumerate(STRATEGY_REGISTRY):
    sid   = cfg["id"]
    sname = cfg["name"]
    smod  = cfg["module"]

    with cols[i % 2]:
        with st.container(border=True):

            # ── 卡片頂部：策略名稱 + 訊號徽章 ──────────────────────────────
            result = run_strategy_cached(sid, smod, _get_ts(sid))

            top_l, top_r = st.columns([3, 2])
            with top_l:
                st.markdown(
                    f"<p style='font-weight:700;font-size:0.95rem;"
                    f"color:#e6edf3;margin:0;padding:0'>{sname}</p>",
                    unsafe_allow_html=True,
                )
            with top_r:
                if result.get("success"):
                    badge_html = _badge_html(
                        result.get("signal", "NEUTRAL"),
                        result.get("recommendation", "觀望"),
                    )
                    st.markdown(
                        f"<div style='text-align:right;padding-top:2px'>"
                        f"{badge_html}</div>",
                        unsafe_allow_html=True,
                    )

            # ── 錯誤顯示 ─────────────────────────────────────────────────────
            if not result.get("success"):
                st.error(f"⚠️ 策略執行錯誤：{result.get('error', '未知錯誤')}")

            else:
                returns: pd.Series = result.get("returns")

                if returns is not None and len(returns) > 0:

                    # ── 指標列 ───────────────────────────────────────────────
                    m = compute_metrics(returns)
                    mc1, mc2, mc3, mc4 = st.columns(4)

                    with mc1:
                        v = m.get("ytd_ret", 0)
                        st.markdown(
                            f"<div class='metric-box'>"
                            f"<div class='metric-val' style='color:{_color(v)}'>{_fmt_pct(v)}</div>"
                            f"<div class='metric-lbl'>YTD</div></div>",
                            unsafe_allow_html=True,
                        )
                    with mc2:
                        v = m.get("total_ret", 0)
                        st.markdown(
                            f"<div class='metric-box'>"
                            f"<div class='metric-val' style='color:{_color(v)}'>{_fmt_pct(v)}</div>"
                            f"<div class='metric-lbl'>總報酬</div></div>",
                            unsafe_allow_html=True,
                        )
                    with mc3:
                        v = m.get("sharpe", 0)
                        c = "#3fb950" if v >= 1 else "#d29922" if v >= 0 else "#f85149"
                        st.markdown(
                            f"<div class='metric-box'>"
                            f"<div class='metric-val' style='color:{c}'>{v:.2f}</div>"
                            f"<div class='metric-lbl'>夏普值</div></div>",
                            unsafe_allow_html=True,
                        )
                    with mc4:
                        v = m.get("max_dd", 0)
                        st.markdown(
                            f"<div class='metric-box'>"
                            f"<div class='metric-val' style='color:#f85149'>{_fmt_pct(v, show_sign=False)}</div>"
                            f"<div class='metric-lbl'>最大回撤</div></div>",
                            unsafe_allow_html=True,
                        )

                    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

                    # ── Plotly 圖表 ──────────────────────────────────────────
                    fig = build_chart(returns, sname)
                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                        config={
                            "displayModeBar": False,
                            "staticPlot": False,
                        },
                        key=f"chart_{sid}_{_get_ts(sid)}",
                    )

                    # ── 策略說明 ─────────────────────────────────────────────
                    if result.get("details"):
                        st.markdown(
                            f"<p class='detail-text'>{result['details']}</p>",
                            unsafe_allow_html=True,
                        )

                else:
                    st.warning("策略未回傳有效的報酬率資料。")

            # ── 卡片底部：時間戳記 + 刷新按鈕 ──────────────────────────────
            st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
            bot_l, bot_r = st.columns([4, 1])
            with bot_l:
                ts_str = result.get("updated_at", "—")
                st.markdown(
                    f"<p class='timestamp'>⏱ 最後更新：{ts_str}</p>",
                    unsafe_allow_html=True,
                )
            with bot_r:
                if st.button("↻ 刷新", key=f"ref_{sid}", use_container_width=True):
                    _touch(sid)
                    st.rerun()
