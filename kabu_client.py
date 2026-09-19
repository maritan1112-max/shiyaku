"""kabuステーションAPI（auカブコム証券）のシンプルなクライアント。

kabuステーションAPIは、kabuステーション（Windows専用アプリ）が起動している
PC上でのみ動作するローカルREST APIであり、クラウドから直接呼び出すことはできない。
このクライアントは、kabuステーションが起動しているマシン上で実行するスクリプト
（trading_bot.py）から利用する。

公式仕様書: https://kabucom.github.io/kabusapi/ptal/
本番/検証(デモ)環境のポート番号や、送信する各コードの意味は、実際に発注する前に
必ず最新の公式仕様書と自分のkabuステーションの設定で確認すること。
"""
import requests


class KabuStationClient:
    def __init__(self, base_url, api_password, timeout=10):
        self.base_url = base_url.rstrip("/")
        self.api_password = api_password
        self.timeout = timeout
        self.token = None

    def login(self):
        resp = requests.post(
            f"{self.base_url}/kabusapi/token",
            json={"APIPassword": self.api_password},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        self.token = resp.json()["Token"]
        return self.token

    def _headers(self):
        if not self.token:
            self.login()
        return {"X-API-KEY": self.token, "Content-Type": "application/json"}

    def get_board(self, symbol, exchange=1):
        resp = requests.get(
            f"{self.base_url}/kabusapi/board/{symbol}@{exchange}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_symbol_info(self, symbol, exchange=1):
        resp = requests.get(
            f"{self.base_url}/kabusapi/symbol/{symbol}@{exchange}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_positions(self, symbol=None):
        params = {"product": 0}
        if symbol:
            params["symbol"] = symbol
        resp = requests.get(
            f"{self.base_url}/kabusapi/positions",
            headers=self._headers(),
            params=params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_cash_wallet(self):
        resp = requests.get(
            f"{self.base_url}/kabusapi/wallet/cash",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def send_order(self, order_password, symbol, side, qty, exchange=1, price=0, front_order_type=10):
        """現物注文を送信する。

        side: "2"=買い, "1"=売り
        front_order_type: 10=成行（本日中）。指定値注文にする場合はprice/expire_dayも変更すること。

        FundType, DelivType, AccountType の値はkabuステーションAPIの仕様変更や
        口座の設定（特定/一般、現物のみ等）によって異なる場合があるため、
        本番発注の前に必ず自分の環境で公式仕様書と照らし合わせて確認すること。
        """
        body = {
            "Password": order_password,
            "Symbol": symbol,
            "Exchange": exchange,
            "SecurityType": 1,
            "Side": side,
            "CashMargin": 1,
            "DelivType": 2,
            "FundType": "AA",
            "AccountType": 2,
            "Qty": qty,
            "FrontOrderType": front_order_type,
            "Price": price,
            "ExpireDay": 0,
        }
        resp = requests.post(
            f"{self.base_url}/kabusapi/sendorder",
            headers=self._headers(),
            json=body,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()
