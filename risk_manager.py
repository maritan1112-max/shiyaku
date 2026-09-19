"""1日の最大損失額と固定注文サイズで自動売買のリスクを管理するモジュール。

状態（本日の損益・取引回数）はJSONファイルに保存し、日付が変わったら
自動的にリセットされる。
"""
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass
class RiskConfig:
    order_size_yen: float
    daily_max_loss_yen: float


class RiskManager:
    def __init__(self, config: RiskConfig, state_path="risk_state.json"):
        self.config = config
        self.state_path = Path(state_path)
        self.state = self._load_state()

    def _default_state(self):
        return {
            "date": date.today().isoformat(),
            "realized_pnl_yen": 0.0,
            "unrealized_pnl_yen": 0.0,
            "trade_count": 0,
        }

    def _load_state(self):
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text())
            if state.get("date") == date.today().isoformat():
                return state
        return self._default_state()

    def _save_state(self):
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2))

    def total_pnl_yen(self):
        return self.state["realized_pnl_yen"] + self.state["unrealized_pnl_yen"]

    def is_stopped(self):
        return self.total_pnl_yen() <= -abs(self.config.daily_max_loss_yen)

    def can_trade(self):
        self.state = self._load_state()
        return not self.is_stopped()

    def sync_unrealized_pnl(self, unrealized_pnl_yen):
        self.state = self._load_state()
        self.state["unrealized_pnl_yen"] = unrealized_pnl_yen
        self._save_state()

    def record_realized_pnl(self, realized_pnl_yen):
        self.state = self._load_state()
        self.state["realized_pnl_yen"] += realized_pnl_yen
        self._save_state()

    def note_order_submitted(self):
        self.state = self._load_state()
        self.state["trade_count"] += 1
        self._save_state()

    def order_quantity(self, price_yen, trading_unit):
        """注文サイズ（円）の予算内で発注可能な株数（単元株の倍数）を返す。"""
        if not price_yen or price_yen <= 0 or not trading_unit or trading_unit <= 0:
            return 0
        units_affordable = int(self.config.order_size_yen // (price_yen * trading_unit))
        return units_affordable * trading_unit
