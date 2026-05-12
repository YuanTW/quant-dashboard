"""
strategy_template.py — 策略腳本範本
====================================
把你現有的策略腳本改成這個格式即可接入儀表板。
需要修改的只有兩件事：
  1. 把你的核心邏輯放入 run() 函式
  2. 最後呼叫 save_outputs() 存檔

儀表板的 Runner 會自動設定 STRATEGY_OUTPUT_DIR 環境變數，
save_outputs() 會把結果存到正確位置。
"""
import os
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# 以下是範例：使用 yfinance 抓台積電資料，計算簡單移動平均交叉策略
# 請把這段換成你自己的邏輯
# ──────────────────────────────────────────────────────────────────────────────
import matplotlib
matplotlib.use("Agg")   # 雲端無 GUI，必須加這行
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import yfinance as yf


def run() -> tuple[str, plt.Figure]:
    """
    執行策略，回傳 (推薦方向文字, matplotlib Figure)

    Returns
    -------
    recommendation : str    例如 "做多" / "做空" / "觀望"
    fig            : Figure 累積損益圖
    """
    # ── 1. 抓資料 ────────────────────────────────────────────────────────────
    ticker = "2330.TW"          # ← 換成你的標的
    df = yf.download(ticker, period="1y", auto_adjust=True, progress=False)
    df = df[["Close"]].copy()
    df.columns = ["close"]
    df.dropna(inplace=True)

    # ── 2. 計算指標（範例：5/20 日移動平均交叉）────────────────────────────────
    df["ma5"]  = df["close"].rolling(5).mean()
    df["ma20"] = df["close"].rolling(20).mean()

    # ── 3. 產生訊號 ──────────────────────────────────────────────────────────
    if df["ma5"].iloc[-1] > df["ma20"].iloc[-1]:
        recommendation = "做多 (MA5 上穿 MA20)"
        signal         = "BUY"
    elif df["ma5"].iloc[-1] < df["ma20"].iloc[-1]:
        recommendation = "做空 (MA5 下穿 MA20)"
        signal         = "SELL"
    else:
        recommendation = "觀望"
        signal         = "HOLD"

    # ── 4. 計算累積損益 ──────────────────────────────────────────────────────
    df["returns"]    = df["close"].pct_change()
    df["cum_return"] = (1 + df["returns"]).cumprod() - 1

    # ── 5. 畫圖 ──────────────────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), dpi=120,
                                    gridspec_kw={"height_ratios": [2, 1]})
    fig.patch.set_facecolor("#0e1117")

    for ax in (ax1, ax2):
        ax.set_facecolor("#1c1f2e")
        ax.tick_params(colors="#9ca3af", labelsize=8)
        ax.spines[:].set_color("#374151")

    # 上圖：價格 + MA
    ax1.plot(df.index, df["close"], color="#60a5fa", linewidth=1.2, label="收盤價")
    ax1.plot(df.index, df["ma5"],   color="#34d399", linewidth=0.9, linestyle="--", label="MA5")
    ax1.plot(df.index, df["ma20"],  color="#f87171", linewidth=0.9, linestyle="--", label="MA20")
    ax1.set_title(f"{ticker}  |  推薦：{recommendation}", color="white", fontsize=11, pad=8)
    ax1.legend(facecolor="#1c1f2e", labelcolor="white", fontsize=8)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))

    # 下圖：累積報酬
    color = "#4ade80" if df["cum_return"].iloc[-1] >= 0 else "#f87171"
    ax2.fill_between(df.index, df["cum_return"] * 100, 0,
                     alpha=0.35, color=color)
    ax2.plot(df.index, df["cum_return"] * 100, color=color, linewidth=1.2)
    ax2.axhline(0, color="#6b7280", linewidth=0.7, linestyle="--")
    ax2.set_ylabel("累積報酬 (%)", color="#9ca3af", fontsize=8)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))

    fig.autofmt_xdate(rotation=30)
    plt.tight_layout(pad=1.5)

    return recommendation, fig, signal


# ──────────────────────────────────────────────────────────────────────────────
# ▼ 以下不需要修改 ▼
# ──────────────────────────────────────────────────────────────────────────────
def save_outputs(recommendation: str, fig: plt.Figure, signal: str = "", details: str = ""):
    """
    把結果存到 STRATEGY_OUTPUT_DIR（由 Runner 自動設定）。
    直接執行此腳本時，存到目前目錄的 ./output/ 資料夾。
    """
    import json
    output_dir = Path(os.environ.get("STRATEGY_OUTPUT_DIR", "./output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # 推薦文字
    (output_dir / "recommendation.txt").write_text(recommendation, encoding="utf-8")

    # 損益圖
    fig.savefig(output_dir / "chart.png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    # result.json（可選，給儀表板顯示更多資訊）
    result = {"signal": signal, "details": details}
    (output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[策略輸出完成] 推薦：{recommendation}，存至：{output_dir}")


if __name__ == "__main__":
    recommendation, fig, signal = run()
    save_outputs(recommendation, fig, signal)
