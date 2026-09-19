"""市場分析 → Claudeによる売買判断 → リスク管理 → kabuステーションAPIでの発注、を
1サイクル実行するスクリプト。

重要: このスクリプトは kabuステーション アプリが起動しているPC上で実行する必要がある
（kabuステーションAPIはローカルAPIのため、クラウド環境からは呼び出せない）。

安全のため、環境変数 DRY_RUN が "false" に設定されない限り、実際の注文は送信せず
判断結果をログとtrade_log.csvに出力するだけの動作になる。実際の資金で発注する前に
必ずDRY_RUNのまま十分に動作を確認すること。
"""
import csv
import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from claude_analyzer import analyze
from kabu_client import KabuStationClient
from risk_manager import RiskConfig, RiskManager

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("trading_bot")

TRADE_LOG_PATH = Path(os.environ.get("TRADE_LOG_PATH", "trade_log.csv"))
TRADE_LOG_FIELDS = ["timestamp", "symbol", "action", "reason", "price", "qty", "dry_run", "order_result"]


def _append_trade_log(row):
    is_new = not TRADE_LOG_PATH.exists()
    with TRADE_LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_LOG_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def _sum_unrealized_pnl(positions):
    # kabuステーションAPIのポジション情報の損益フィールド名は口座種別やAPIの
    # バージョンによって異なる場合がある。実際のレスポンスを確認し、必要なら
    # キー名を調整すること。
    return sum(p.get("ProfitLoss", 0) or 0 for p in positions)


def run_once(symbols, dry_run=True):
    client = KabuStationClient(
        base_url=os.environ["KABU_API_BASE_URL"],
        api_password=os.environ["KABU_API_PASSWORD"],
    )
    risk_manager = RiskManager(
        RiskConfig(
            order_size_yen=float(os.environ.get("ORDER_SIZE_YEN", "10000")),
            daily_max_loss_yen=float(os.environ.get("DAILY_MAX_LOSS_YEN", "5000")),
        ),
        state_path=os.environ.get("RISK_STATE_PATH", "risk_state.json"),
    )

    try:
        positions = client.get_positions()
        risk_manager.sync_unrealized_pnl(_sum_unrealized_pnl(positions))
    except Exception:
        logger.exception("ポジション取得に失敗したため、本日の損益状況を更新できませんでした。")

    if not risk_manager.can_trade():
        logger.warning("本日の最大損失額に達したため、新規注文を停止しています。")
        return

    for symbol in symbols:
        try:
            board = client.get_board(symbol)
            symbol_info = client.get_symbol_info(symbol)
        except Exception:
            logger.exception("%s の価格取得に失敗しました。スキップします。", symbol)
            continue

        current_price = board.get("CurrentPrice")
        market_data = {
            "現在値": current_price,
            "前日比": board.get("ChangePreviousClose"),
            "始値": board.get("OpeningPrice"),
            "高値": board.get("HighPrice"),
            "安値": board.get("LowPrice"),
        }
        decision = analyze(symbol_info.get("DisplayName", symbol), market_data)
        logger.info("%s: %s (%s)", symbol, decision["action"], decision["reason"])

        row = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "symbol": symbol,
            "action": decision["action"],
            "reason": decision["reason"],
            "price": current_price,
            "qty": 0,
            "dry_run": dry_run,
            "order_result": "",
        }

        if decision["action"] == "HOLD":
            _append_trade_log(row)
            continue

        trading_unit = symbol_info.get("TradingUnit", 100)
        qty = risk_manager.order_quantity(current_price, trading_unit)
        if qty <= 0:
            row["order_result"] = "注文サイズ(ORDER_SIZE_YEN)が単元株購入に不足のため見送り"
            _append_trade_log(row)
            continue
        row["qty"] = qty

        side = "2" if decision["action"] == "BUY" else "1"
        if dry_run:
            row["order_result"] = "DRY_RUNのため未発注"
            logger.info("[DRY_RUN] %s を%s株、%sする想定です。", symbol, qty, decision["action"])
        else:
            try:
                result = client.send_order(
                    order_password=os.environ["KABU_ORDER_PASSWORD"],
                    symbol=symbol,
                    side=side,
                    qty=qty,
                )
                row["order_result"] = str(result)
                risk_manager.note_order_submitted()
                logger.info("発注結果: %s", result)
            except Exception:
                logger.exception("%s の発注に失敗しました。", symbol)
                row["order_result"] = "発注失敗"

        _append_trade_log(row)


if __name__ == "__main__":
    symbols_env = os.environ.get("SYMBOLS", "")
    symbols = [s.strip() for s in symbols_env.split(",") if s.strip()]
    if not symbols:
        raise SystemExit("環境変数 SYMBOLS に証券コードをカンマ区切りで設定してください（例: 7203,9984）")

    dry_run = os.environ.get("DRY_RUN", "true").lower() != "false"
    if not dry_run:
        logger.warning("DRY_RUN=false: 実際の資金で自動発注します。")

    run_once(symbols, dry_run=dry_run)
