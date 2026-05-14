"""
app.py — 量化交易儀表板 v2
===========================
首頁  : 2 欄策略卡 · 近一年累積報酬圖 · 圈選/滾輪縮放
詳情頁: 左側導航進入 · 6 大統計指標 · 多段期間選擇 · 累積報酬 + 回撤雙圖
"""

import importlib
import os
import sys
import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pytz
import streamlit as st

# ── 路徑 ──────────────────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

TW = pytz.timezone("Asia/Taipei")

# ══════════════════════════════════════════════════════════════════════════════
#  策略登錄表  ← 在此新增策略
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
    # {"id": "my_strat", "name": "我的策略", "module": "strategies.my_strat"},
]

# ══════════════════════════════════════════════════════════════════════════════
#  頁面設定
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="量化交易儀表板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
#  CSS — 深色專業主題
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
/* ── 全域 ───────────────────────────────────────────────────────────────── */
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stMain"] > div {
    background-color: #0d1117 !important;
    color: #e6edf3 !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
[data-testid="stSidebar"] {
    background-color: #010409 !important;
    border-right: 1px solid #21262d !important;
}
/* 隱藏不必要元素 */
#MainMenu, footer, header { visibility: hidden !important; }
.stDeployButton, div[data-testid="stToolbar"] { display: none !important; }

/* ── Sidebar ────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: none !important;
    color: #8b949e !important;
    text-align: left !important;
    font-size: 0.83rem !important;
    font-weight: 500 !important;
    padding: 6px 10px !important;
    border-radius: 6px !important;
    width: 100% !important;
    transition: background 0.15s, color 0.15s !important;
    margin-bottom: 1px !important;
    justify-content: flex-start !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: #161b22 !important;
    color: #e6edf3 !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: rgba(31,111,235,0.12) !important;
    color: #58a6ff !important;
    border-left: 2px solid #1f6feb !important;
    border-radius: 0 6px 6px 0 !important;
    font-weight: 600 !important;
}

/* ── 卡片（border container）────────────────────────────────────────────── */
div[data-testid="stVerticalBlockBorderWrapper"] > div {
    background: #161b22 !important;
    border: 1px solid #21262d !important;
    border-radius: 14px !important;
    padding: 1.1rem 1.25rem 1rem !important;
    transition: border-color 0.2s, box-shadow 0.25s !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div:hover {
    border-color: #30363d !important;
    box-shadow: 0 6px 30px rgba(0,0,0,0.45) !important;
}

/* ── 訊號徽章 ───────────────────────────────────────────────────────────── */
.badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 11px; border-radius: 20px;
    font-size: 0.74rem; font-weight: 700; letter-spacing: 0.35px;
    white-space: nowrap;
}
.b-long    { background:rgba(63,185,80,.13);  color:#3fb950; border:1px solid rgba(63,185,80,.3); }
.b-short   { background:rgba(248,81,73,.13);  color:#f85149; border:1px solid rgba(248,81,73,.3); }
.b-neutral { background:rgba(210,153,34,.13); color:#d29922; border:1px solid rgba(210,153,34,.3); }

/* ── 指標 ───────────────────────────────────────────────────────────────── */
.met      { text-align:center; padding:6px 2px 8px; }
.met-v    { font-size:1.1rem; font-weight:700; line-height:1.25; }
.met-l    { font-size:0.65rem; color:#6e7681; margin-top:3px;
            text-transform:uppercase; letter-spacing:0.5px; }

/* ── 詳情頁 stat cards ──────────────────────────────────────────────────── */
.sc {
    background:#161b22; border:1px solid #21262d; border-radius:10px;
    padding:14px 10px; text-align:center;
}
.sc-v { font-size:1.25rem; font-weight:700; }
.sc-l { font-size:0.65rem; color:#6e7681; margin-top:4px;
        text-transform:uppercase; letter-spacing:0.5px; }

/* ── 頁面標題 ───────────────────────────────────────────────────────────── */
.ph { padding:0.85rem 0 0.8rem; border-bottom:1px solid #21262d; margin-bottom:1.2rem; }
.pt { font-size:1.35rem; font-weight:700; color:#e6edf3; margin:0; }
.ps { font-size:0.75rem; color:#8b949e; margin:5px 0 0; }

/* ── 分析框 ─────────────────────────────────────────────────────────────── */
.analysis {
    background: #0d1117;
    border: 1px solid #21262d;
    border-left: 3px solid #1f6feb;
    border-radius: 0 8px 8px 0;
    padding: 10px 14px;
    font-size: 0.8rem; color: #8b949e; line-height: 1.65;
    margin-top: 10px;
}

/* ── 分隔線 ─────────────────────────────────────────────────────────────── */
.div { border-top:1px solid #21262d; margin:9px 0; }

/* ── 時間戳 ─────────────────────────────────────────────────────────────── */
.ts { font-size:0.68rem; color:#6e7681; margin:0; }

/* ── 段期按鈕 ───────────────────────────────────────────────────────────── */
.stButton > button[kind="secondary"] {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #8b949e !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    padding: 4px 0 !important;
    border-radius: 6px !important;
}
.stButton > button[kind="secondary"]:hover {
    border-color: #58a6ff !important;
    color: #e6edf3 !important;
}
.stButton > button[kind="primary"] {
    background: #1f6feb !important;
    border: none !important;
    color: #fff !important;
    font-size: 0.8rem !important;
    font-weight: 700 !important;
    padding: 4px 0 !important;
    border-radius: 6px !important;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Session State
# ══════════════════════════════════════════════════════════════════════════════
_DEFAULTS = {"page": "home", "ts": {}, "period": {}}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ══════════════════════════════════════════════════════════════════════════════
#  策略執行（快取）
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600, show_spinner=False)
def _load(sid: str, module: str, _ts: float) -> dict:
    try:
        mod = importlib.import_module(module)
        importlib.reload(mod)
        r = mod.run()
        r["success"] = True
    except Exception as e:
        r = {"success": False, "error": str(e)}
    r["updated_at"] = datetime.now(TW).strftime("%Y/%m/%d %H:%M")
    return r


def get_result(cfg: dict) -> dict:
    return _load(cfg["id"], cfg["module"], st.session_state.ts.get(cfg["id"], 0.0))


# ══════════════════════════════════════════════════════════════════════════════
#  績效指標
# ══════════════════════════════════════════════════════════════════════════════
def metrics(ret: pd.Series) -> dict:
    if ret is None or len(ret) < 2:
        return {}
    cum   = (1 + ret).cumprod() - 1
    total = float(cum.iloc[-1])
    n_yr  = len(ret) / 252
    ann   = float((1 + total) ** (1 / max(n_yr, 0.01)) - 1)
    sh    = float(ret.mean() / ret.std() * np.sqrt(252)) if ret.std() > 0 else 0.0
    w     = (1 + ret).cumprod()
    mdd   = float(((w - w.cummax()) / w.cummax()).min())
    wr    = float((ret > 0).mean())
    today = pd.Timestamp(date.today())
    ytd_r = ret[ret.index >= pd.Timestamp(date.today().year, 1, 1)]
    ytd   = float((1 + ytd_r).prod() - 1) if len(ytd_r) > 0 else 0.0
    r1y_r = ret[ret.index >= today - pd.Timedelta(days=365)]
    r1y   = float((1 + r1y_r).prod() - 1) if len(r1y_r) > 0 else 0.0
    return dict(total=total, ann=ann, sharpe=sh, mdd=mdd, wr=wr, ytd=ytd, r1y=r1y)


# ══════════════════════════════════════════════════════════════════════════════
#  圖表建構
# ══════════════════════════════════════════════════════════════════════════════
_BASE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter,sans-serif", color="#8b949e", size=11),
    showlegend=False,
    dragmode="zoom",
    modebar_bgcolor="rgba(13,17,23,0.7)",
    modebar_color="#6e7681",
    modebar_activecolor="#58a6ff",
)
_XAX = dict(
    showgrid=False, showline=False, zeroline=False,
    tickfont=dict(color="#6e7681", size=10),
    type="date", rangeslider=dict(visible=False),
)
_YAX = dict(
    showgrid=True, gridcolor="rgba(33,38,45,0.6)",
    showline=False, zeroline=False,
    tickfont=dict(color="#6e7681", size=10),
    ticksuffix="%", side="right",
)


def _cum_trace(ret: pd.Series, name="累積報酬") -> go.Scatter:
    cum   = (1 + ret).cumprod() - 1
    final = float(cum.iloc[-1]) if len(cum) else 0
    lc = "#3fb950" if final >= 0 else "#f85149"
    fc = "rgba(63,185,80,0.08)" if final >= 0 else "rgba(248,81,73,0.08)"
    return go.Scatter(
        x=cum.index, y=(cum.values * 100).round(3),
        mode="lines", fill="tozeroy", fillcolor=fc,
        line=dict(color=lc, width=1.9), name=name,
        hovertemplate="<b>%{x|%Y/%m/%d}</b><br>累積報酬：%{y:.2f}%<extra></extra>",
    )


def _dd_trace(ret: pd.Series) -> go.Scatter:
    w  = (1 + ret).cumprod()
    dd = ((w - w.cummax()) / w.cummax()) * 100
    return go.Scatter(
        x=dd.index, y=dd.values.round(3),
        mode="lines", fill="tozeroy",
        fillcolor="rgba(248,81,73,0.09)",
        line=dict(color="#f85149", width=1.3), name="回撤",
        hovertemplate="<b>%{x|%Y/%m/%d}</b><br>回撤：%{y:.2f}%<extra></extra>",
    )


def build_home_chart(ret: pd.Series) -> go.Figure:
    """首頁卡片：近一年，圈選縮放。"""
    cutoff = pd.Timestamp(date.today() - timedelta(days=365))
    r = ret[ret.index >= cutoff]
    if len(r) == 0:
        r = ret
    fig = go.Figure(_cum_trace(r))
    fig.add_hline(y=0, line_dash="dot",
                  line_color="rgba(139,148,158,0.18)", line_width=1)
    fig.update_layout(**_BASE_LAYOUT, height=185,
                      margin=dict(l=0, r=0, t=6, b=0))
    fig.update_xaxes(**_XAX)
    fig.update_yaxes(**_YAX)
    return fig


def build_detail_chart(ret: pd.Series, period: str) -> go.Figure:
    """詳情頁：選定時段，累積報酬 + 回撤雙圖。"""
    today = date.today()
    cuts  = {
        "3M":  today - timedelta(days=90),
        "6M":  today - timedelta(days=180),
        "YTD": date(today.year, 1, 1),
        "1Y":  today - timedelta(days=365),
        "2Y":  today - timedelta(days=730),
        "ALL": None,
    }
    cut = cuts.get(period)
    r   = ret[ret.index >= pd.Timestamp(cut)] if cut else ret
    if len(r) < 2:
        r = ret

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.66, 0.34],
        vertical_spacing=0.03,
    )
    fig.add_trace(_cum_trace(r), row=1, col=1)
    fig.add_hline(y=0, line_dash="dot",
                  line_color="rgba(139,148,158,0.18)", line_width=1, row=1, col=1)
    fig.add_trace(_dd_trace(r), row=2, col=1)

    fig.update_layout(
        **_BASE_LAYOUT,
        height=440,
        margin=dict(l=0, r=0, t=8, b=0),
        annotations=[
            dict(text="累積報酬", xref="paper", yref="paper",
                 x=0.01, y=0.99, showarrow=False,
                 font=dict(color="#8b949e", size=10.5), xanchor="left", yanchor="top"),
            dict(text="最大回撤", xref="paper", yref="paper",
                 x=0.01, y=0.31, showarrow=False,
                 font=dict(color="#8b949e", size=10.5), xanchor="left", yanchor="top"),
        ],
    )
    fig.update_yaxes(**_YAX, row=1, col=1)
    fig.update_yaxes(**_YAX, row=2, col=1)
    fig.update_xaxes(**_XAX, row=1, col=1, showticklabels=False)
    fig.update_xaxes(**_XAX, row=2, col=1)
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  小工具
# ══════════════════════════════════════════════════════════════════════════════
def _c(v: float) -> str:
    return "#3fb950" if v >= 0 else "#f85149"


def _fp(v: float, sign: bool = True) -> str:
    s = "+" if v >= 0 and sign else ""
    return f"{s}{v * 100:.2f}%"


def _badge(signal: str, rec: str) -> str:
    cls  = {"LONG": "b-long", "SHORT": "b-short"}.get(signal, "b-neutral")
    icon = {"LONG": "▲", "SHORT": "▼"}.get(signal, "●")
    return f'<span class="badge {cls}">{icon}&nbsp;{rec}</span>'


_CHART_CFG = {
    "displayModeBar": True,
    "modeBarButtonsToKeep": ["zoom2d", "pan2d", "zoomIn2d", "zoomOut2d", "resetScale2d"],
    "scrollZoom": True,
    "displaylogo": False,
}


# ══════════════════════════════════════════════════════════════════════════════
#  側邊欄
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div style="padding:1.1rem 0.6rem 0.9rem;
                border-bottom:1px solid #21262d; margin-bottom:0.6rem;">
        <p style="font-size:0.98rem;font-weight:700;color:#e6edf3;margin:0;
                  letter-spacing:-0.2px">📈 量化交易儀表板</p>
        <p style="font-size:0.68rem;color:#6e7681;margin:4px 0 0">
            Quant Trading Dashboard</p>
    </div>
    """, unsafe_allow_html=True)

    # 總覽按鈕
    is_home = st.session_state.page == "home"
    if st.button("🏠  總覽",
                 key="nav_home",
                 type="primary" if is_home else "secondary",
                 use_container_width=True):
        st.session_state.page = "home"
        st.rerun()

    st.markdown("""
    <p style="font-size:0.63rem;color:#6e7681;
              padding:10px 8px 4px;margin:0;
              text-transform:uppercase;letter-spacing:0.7px;">策略</p>
    """, unsafe_allow_html=True)

    # 各策略導航
    for cfg in STRATEGY_REGISTRY:
        is_active = (st.session_state.page == cfg["id"])
        res = get_result(cfg)
        sig = res.get("signal", "NEUTRAL") if res.get("success") else "NEUTRAL"
        dot = {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "🟡"}.get(sig, "⚪")
        if st.button(f"{dot}  {cfg['name']}",
                     key=f"nav_{cfg['id']}",
                     type="primary" if is_active else "secondary",
                     use_container_width=True):
            st.session_state.page = cfg["id"]
            st.rerun()

    # 全部刷新
    st.markdown("""
    <div style="border-top:1px solid #21262d;margin:14px 0 8px;"></div>
    """, unsafe_allow_html=True)
    if st.button("🔄  全部刷新", use_container_width=True):
        t = time.time()
        for c in STRATEGY_REGISTRY:
            st.session_state.ts[c["id"]] = t
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  首頁
# ══════════════════════════════════════════════════════════════════════════════
def render_home():
    st.markdown("""
    <div class="ph">
        <p class="pt">策略總覽</p>
        <p class="ps">
            點擊左側策略名稱查看詳細統計 &nbsp;·&nbsp;
            圖表可<strong style="color:#58a6ff">拖曳圈選縮放</strong>，滾輪縮放，雙擊還原
        </p>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(2, gap="medium")
    for i, cfg in enumerate(STRATEGY_REGISTRY):
        with cols[i % 2]:
            with st.container(border=True):
                res = get_result(cfg)
                ret = res.get("returns") if res.get("success") else None
                m   = metrics(ret) if ret is not None else {}

                # ── 標題列 ───────────────────────────────────────────────
                tl, tr = st.columns([3, 2])
                with tl:
                    st.markdown(
                        f"<p style='font-weight:700;font-size:0.9rem;"
                        f"color:#e6edf3;margin:0;letter-spacing:-0.1px'>"
                        f"{cfg['name']}</p>",
                        unsafe_allow_html=True)
                with tr:
                    if res.get("success"):
                        b = _badge(res.get("signal", "NEUTRAL"),
                                   res.get("recommendation", "觀望"))
                        st.markdown(
                            f"<div style='text-align:right;padding-top:2px'>{b}</div>",
                            unsafe_allow_html=True)

                if not res.get("success"):
                    st.error(f"⚠️ {res.get('error', '未知錯誤')}")

                elif ret is not None and len(ret) > 0:
                    # ── 快速指標 ─────────────────────────────────────────
                    qa, qb = st.columns(2)
                    with qa:
                        v = m.get("r1y", 0)
                        st.markdown(
                            f"<div class='met'>"
                            f"<div class='met-v' style='color:{_c(v)}'>{_fp(v)}</div>"
                            f"<div class='met-l'>近一年報酬</div></div>",
                            unsafe_allow_html=True)
                    with qb:
                        v = m.get("sharpe", 0)
                        c = "#3fb950" if v >= 1 else "#d29922" if v >= 0 else "#f85149"
                        st.markdown(
                            f"<div class='met'>"
                            f"<div class='met-v' style='color:{c}'>{v:.2f}</div>"
                            f"<div class='met-l'>夏普值</div></div>",
                            unsafe_allow_html=True)

                    st.markdown("<div class='div'></div>", unsafe_allow_html=True)

                    # ── 近一年圖表（可縮放）───────────────────────────────
                    fig = build_home_chart(ret)
                    st.plotly_chart(
                        fig, use_container_width=True,
                        config=_CHART_CFG,
                        key=f"hc_{cfg['id']}",
                    )

                # ── 底部列 ───────────────────────────────────────────────
                st.markdown("<div class='div'></div>", unsafe_allow_html=True)
                bl, br = st.columns([4, 1])
                with bl:
                    st.markdown(
                        f"<p class='ts'>⏱ {res.get('updated_at', '—')}</p>",
                        unsafe_allow_html=True)
                with br:
                    if st.button("↻", key=f"ref_{cfg['id']}",
                                 use_container_width=True, help="重新執行策略"):
                        st.session_state.ts[cfg["id"]] = time.time()
                        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  詳情頁
# ══════════════════════════════════════════════════════════════════════════════
def render_detail(cfg: dict):
    res = get_result(cfg)
    ret = res.get("returns") if res.get("success") else None
    m   = metrics(ret) if ret is not None else {}

    # ── 頂部操作列 ────────────────────────────────────────────────────────
    bk, _, rf = st.columns([1, 5, 1])
    with bk:
        if st.button("← 返回總覽", type="secondary"):
            st.session_state.page = "home"
            st.rerun()
    with rf:
        if st.button("↻ 刷新", type="secondary", use_container_width=True):
            st.session_state.ts[cfg["id"]] = time.time()
            st.rerun()

    # ── 頁面標題 ──────────────────────────────────────────────────────────
    badge_html = (_badge(res.get("signal", "NEUTRAL"), res.get("recommendation", "觀望"))
                  if res.get("success") else "")
    st.markdown(f"""
    <div class="ph">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
            <p class="pt">{cfg['name']}</p>
            {badge_html}
        </div>
        <p class="ps">
            ⏱ 最後更新：{res.get('updated_at', '—')} &nbsp;·&nbsp;
            拖曳圈選縮放 · 滾輪縮放 · 雙擊還原
        </p>
    </div>
    """, unsafe_allow_html=True)

    if not res.get("success"):
        st.error(f"策略執行錯誤：{res.get('error', '未知錯誤')}")
        return
    if ret is None or len(ret) < 2:
        st.warning("策略未回傳有效的報酬率資料。")
        return

    # ── 6 大統計指標卡 ────────────────────────────────────────────────────
    STATS = [
        ("YTD",    m.get("ytd",   0), "pct"),
        ("近一年",  m.get("r1y",   0), "pct"),
        ("總報酬",  m.get("total", 0), "pct"),
        ("年化報酬", m.get("ann",  0), "pct"),
        ("夏普值",  m.get("sharpe",0), "num"),
        ("最大回撤", m.get("mdd",  0), "abs"),
    ]
    scols = st.columns(6)
    for col, (lbl, val, fmt) in zip(scols, STATS):
        with col:
            if fmt == "pct":
                disp, color = _fp(val), _c(val)
            elif fmt == "abs":
                disp, color = f"{val*100:.2f}%", "#f85149"
            else:
                disp = f"{val:.2f}"
                color = "#3fb950" if val >= 1 else "#d29922" if val >= 0 else "#f85149"
            st.markdown(
                f"<div class='sc'>"
                f"<div class='sc-v' style='color:{color}'>{disp}</div>"
                f"<div class='sc-l'>{lbl}</div></div>",
                unsafe_allow_html=True)

    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)

    # ── 時段選擇 ──────────────────────────────────────────────────────────
    PERIODS = ["3M", "6M", "YTD", "1Y", "2Y", "ALL"]
    cur = st.session_state.period.get(cfg["id"], "1Y")

    period_cols = st.columns(len(PERIODS))
    for j, p in enumerate(PERIODS):
        with period_cols[j]:
            if st.button(p, key=f"p_{cfg['id']}_{p}",
                         type="primary" if p == cur else "secondary",
                         use_container_width=True):
                st.session_state.period[cfg["id"]] = p
                st.rerun()

    # ── 雙圖（累積報酬 + 回撤）───────────────────────────────────────────
    fig = build_detail_chart(ret, cur)
    st.plotly_chart(
        fig, use_container_width=True,
        config=_CHART_CFG,
        key=f"dc_{cfg['id']}_{cur}",
    )

    # ── 策略分析說明 ──────────────────────────────────────────────────────
    if res.get("details"):
        st.markdown(
            f"<div class='analysis'>"
            f"💡 <strong style='color:#c9d1d9'>分析說明</strong><br>"
            f"{res['details']}</div>",
            unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  路由
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.page == "home":
    render_home()
else:
    found = next((c for c in STRATEGY_REGISTRY
                  if c["id"] == st.session_state.page), None)
    if found:
        render_detail(found)
    else:
        st.session_state.page = "home"
        st.rerun()
