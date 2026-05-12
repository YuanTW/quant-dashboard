"""
telegram_notifier.py — Telegram 推播模組
使用 python-telegram-bot 發送訊息 & 圖片

設定方式：
  1. 在 Telegram 搜尋 @BotFather，輸入 /newbot 建立 Bot，取得 BOT_TOKEN
  2. 對你的 Bot 發一則訊息，然後開啟瀏覽器：
     https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
     從回傳的 JSON 取得你的 chat_id
  3. 將 BOT_TOKEN 和 CHAT_ID 填入 .env
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


def _get_bot():
    """建立 Bot 實例（懶初始化）"""
    import telegram  # type: ignore
    if not config.TELEGRAM_BOT_TOKEN:
        raise ValueError("請在 .env 設定 TELEGRAM_BOT_TOKEN")
    return telegram.Bot(token=config.TELEGRAM_BOT_TOKEN)


def is_configured() -> bool:
    """檢查 Telegram 是否已設定"""
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def send_text(message: str) -> bool:
    """發送純文字訊息"""
    if not is_configured():
        logger.warning("Telegram 未設定，略過發送")
        return False
    try:
        import asyncio
        bot = _get_bot()
        asyncio.run(
            bot.send_message(
                chat_id    = config.TELEGRAM_CHAT_ID,
                text       = message,
                parse_mode = "HTML",
            )
        )
        return True
    except Exception as exc:
        logger.error("Telegram 發送失敗：%s", exc)
        return False


def send_photo(image_path: str, caption: str = "") -> bool:
    """發送圖片（附說明文字）"""
    if not is_configured():
        return False
    try:
        import asyncio
        bot = _get_bot()
        with open(image_path, "rb") as f:
            asyncio.run(
                bot.send_photo(
                    chat_id = config.TELEGRAM_CHAT_ID,
                    photo   = f,
                    caption = caption,
                )
            )
        return True
    except Exception as exc:
        logger.error("Telegram 圖片發送失敗：%s", exc)
        return False


def notify_strategy_result(
    strategy_name: str,
    recommendation: str,
    signal: str,
    details: Optional[str]  = None,
    chart_path: Optional[str] = None,
):
    """
    策略執行完成後發送完整通知。
    會先發送一則格式化文字訊息，若有損益圖則再傳一張圖片。
    """
    # ── 訊號 Emoji 對應 ──────────────────────────────────────────────────────
    signal_emoji = {
        "BUY":  "🟢",
        "SELL": "🔴",
        "HOLD": "🟡",
    }.get(signal.upper() if signal else "", "⚪")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"📊 <b>{strategy_name}</b>",
        f"🕐 {now}",
        "─────────────────",
        f"{signal_emoji} <b>推薦方向</b>：{recommendation}",
    ]
    if details:
        lines.append(f"\n📝 {details}")

    message = "\n".join(lines)

    ok_text = send_text(message)

    if chart_path and Path(chart_path).exists():
        send_photo(chart_path, caption=f"{strategy_name} — 累積損益圖")

    return ok_text


def notify_error(strategy_name: str, error_message: str):
    """策略執行失敗通知"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = (
        f"⚠️ <b>{strategy_name}</b> 執行失敗\n"
        f"🕐 {now}\n"
        f"─────────────────\n"
        f"❌ {error_message}"
    )
    send_text(msg)
