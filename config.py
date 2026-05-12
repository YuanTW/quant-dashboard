"""
config.py — 統一設定管理
本地開發：從 .env 讀取
Streamlit Cloud：從 st.secrets 讀取（Settings → Secrets）
Railway：從環境變數讀取
"""
import os

# 嘗試載入 .env（本地開發用，雲端不需要）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 從環境變數或 Streamlit secrets 讀取設定
def _get(key: str, default: str = "") -> str:
    val = os.getenv(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default

# ── 資料庫 ────────────────────────────────────────────────────────────────────
DATABASE_URL = _get("DATABASE_URL", "sqlite:///quant_dashboard.db")

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = _get("TELEGRAM_CHAT_ID", "")

# ── 路徑 ──────────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
STRATEGIES_DIR = os.path.join(BASE_DIR, "strategies")
OUTPUTS_DIR    = os.path.join(BASE_DIR, "outputs")

# ── 顯示設定 ──────────────────────────────────────────────────────────────────
DASHBOARD_TITLE    = _get("DASHBOARD_TITLE", "量化交易儀表板")
DASHBOARD_SUBTITLE = _get("DASHBOARD_SUBTITLE", "Quantitative Trading Monitor")
TIMEZONE           = _get("TIMEZONE", "Asia/Taipei")
