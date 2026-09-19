"""Claude APIを使って、与えられた価格情報からBUY/SELL/HOLDを判断する。"""
import json
import os

from anthropic import Anthropic

_SYSTEM_PROMPT = """あなたは日本株の短期売買を支援するアシスタントです。
与えられた銘柄の価格情報のみに基づき、BUY・SELL・HOLDのいずれかを判断してください。
根拠が乏しい、または情報が不十分な場合は必ずHOLDを選んでください。
出力は次のJSON形式のみで返してください（説明文やコードブロックは付けないこと）:
{"action": "BUY または SELL または HOLD", "reason": "40文字程度の短い理由"}
"""


def analyze(symbol_name, market_data, api_key=None, model="claude-sonnet-5"):
    client = Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=model,
        max_tokens=300,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"銘柄: {symbol_name}\n価格情報: {json.dumps(market_data, ensure_ascii=False)}",
            }
        ],
    )
    text = message.content[0].text.strip()
    try:
        decision = json.loads(text)
    except json.JSONDecodeError:
        decision = {"action": "HOLD", "reason": f"応答の解析に失敗したため見送り: {text[:100]}"}

    if decision.get("action") not in ("BUY", "SELL", "HOLD"):
        decision = {"action": "HOLD", "reason": "不正な応答のため見送り"}

    return decision
