"""投資運用ダッシュボード。

実際の自動発注（trading_bot.py）は kabuステーションが起動しているPC上で実行する
必要があるため、このダッシュボードはその実行結果（trade_log.csv / risk_state.json）
を表示するだけの画面。同じディレクトリでtrading_bot.pyを実行した場合に内容が反映される。
"""
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="投資運用ダッシュボード", layout="wide")
st.title("投資運用ダッシュボード（Claude連携・auカブコム証券）")

st.info(
    "実際の自動発注は、kabuステーションが起動しているPC上で `trading_bot.py` を実行して行います。"
    "このダッシュボードはその実行結果を表示するだけで、ここから発注はできません。"
)

risk_state_path = Path(os.environ.get("RISK_STATE_PATH", "risk_state.json"))
trade_log_path = Path(os.environ.get("TRADE_LOG_PATH", "trade_log.csv"))

st.subheader("本日のリスク状況")
if risk_state_path.exists():
    state = json.loads(risk_state_path.read_text())
    col1, col2, col3 = st.columns(3)
    col1.metric("日付", state.get("date", "-"))
    total_pnl = state.get("realized_pnl_yen", 0) + state.get("unrealized_pnl_yen", 0)
    col2.metric("本日の損益（円）", f"{total_pnl:,.0f}")
    col3.metric("本日の発注件数", state.get("trade_count", 0))
else:
    st.warning("risk_state.json が見つかりません。まだ trading_bot.py が実行されていません。")

st.subheader("取引ログ")
if trade_log_path.exists():
    df = pd.read_csv(trade_log_path)
    st.dataframe(df.sort_values("timestamp", ascending=False), use_container_width=True)
else:
    st.warning("trade_log.csv が見つかりません。")
