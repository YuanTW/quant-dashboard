"""
config.py — 統一設定管理
所有環境變數都從 .env 讀取，部署到 Railway 時在平台上設定即可
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── 資料庫 ──────────────────────────────────────────────────────────────────
# Railway 提供 PostgreSQL 時會自動注入 DATABASE_URL
# 本地開發不設定則使用 SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///quant_dashboard.db")

# ── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── 路徑 ────────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
STRATEGIES_DIR = os.path.join(BASE_DIR, "strategies")
OUTPUTS_DIR    = os.path.join(BASE_DIR, "outputs")

# ── 儀表板顯示 ───────────────────────────────────────────────────────────────
DASHBOARD_TITLE    = os.getenv("DASHBOARD_TITLE", "量化交易儀表板")
DASHBOARD_SUBTITLE = os.getenv("DASHBOARD_SUBTITLE", "Quantitative Trading Monitor")
TIMEZONE           = os.getenv("TIMEZONE", "Asia/Taipei")
