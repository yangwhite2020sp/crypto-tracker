"""
CryptoTracker Pro - 通知推送模块
支持飞书 Webhook 和 企业微信 Webhook
"""
import json
import requests
from datetime import datetime
from config import FEISHU_WEBHOOK, WECHAT_WEBHOOK, HTTP_PROXY, HTTPS_PROXY, USE_PROXY

PROXIES = {}
if USE_PROXY:
    PROXIES = {"http": HTTP_PROXY, "https": HTTPS_PROXY}


class Notifier:
    def __init__(self):
        self.feishu_webhook = FEISHU_WEBHOOK
        self.wechat_webhook = WECHAT_WEBHOOK
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if PROXIES:
            self.session.proxies.update(PROXIES)

    def send_message(self, title, content, score=None, direction=None):
        """发送消息到所有配置的渠道"""
        results = {}

        if self.feishu_webhook:
            results["feishu"] = self._send_feishu(title, content, score, direction)

        if self.wechat_webhook:
            results["wechat"] = self._send_wechat(title, content, score, direction)

        return results

    def _send_feishu(self, title, content, score=None, direction=None):
        """发送飞书消息（富文本卡片）"""
        try:
            # 根据方向选颜色
            color_map = {
                "STRONG_BUY": "green",
                "BUY": "blue",
                "HOLD": "grey",
                "SELL": "orange",
                "STRONG_SELL": "red",
            }
            color = color_map.get(direction, "grey")

            # 方向emoji
            emoji_map = {
                "STRONG_BUY": "🟢🟢",
                "BUY": "🟢",
                "HOLD": "🟡",
                "SELL": "🟠",
                "STRONG_SELL": "🔴🔴",
            }
            emoji = emoji_map.get(direction, "⚪")

            card = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": f"{emoji} {title}"},
                        "template": color,
                    },
                    "elements": [
                        {"tag": "markdown", "content": content},
                        {"tag": "hr"},
                        {
                            "tag": "note",
                            "elements": [
                                {
                                    "tag": "plain_text",
                                    "content": f"CryptoTracker Pro | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                                }
                            ],
                        },
                    ],
                },
            }

            resp = self.session.post(self.feishu_webhook, json=card, timeout=10)
            if resp.status_code == 200 and resp.json().get("code") == 0:
                return True
            else:
                print(f"[Notifier] 飞书发送失败: {resp.text}")
                return False
        except Exception as e:
            print(f"[Notifier] 飞书异常: {e}")
            return False

    def _send_wechat(self, title, content, score=None, direction=None):
        """发送企业微信消息（Markdown）"""
        try:
            msg = {
                "msgtype": "markdown",
                "markdown": {
                    "content": f"## {title}\n\n{content}\n\n> 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                },
            }

            resp = self.session.post(self.wechat_webhook, json=msg, timeout=10)
            if resp.status_code == 200 and resp.json().get("errcode") == 0:
                return True
            else:
                print(f"[Notifier] 微信发送失败: {resp.text}")
                return False
        except Exception as e:
            print(f"[Notifier] 微信异常: {e}")
            return False

    def send_signal_alert(self, symbol, analysis_result):
        """发送策略信号告警"""
        direction = analysis_result.get("direction", "HOLD")
        score = analysis_result.get("total_score", 0)
        price = analysis_result.get("price", 0)
        details = analysis_result.get("details", {})

        # 只发送重要信号
        if direction == "HOLD":
            return None

        emoji_map = {
            "STRONG_BUY": "🟢🟢 强烈买入",
            "BUY": "🟢 买入",
            "SELL": "🟠 卖出",
            "STRONG_SELL": "🔴🔴 强烈卖出",
        }
        dir_text = emoji_map.get(direction, "⚪ 观望")

        title = f"{symbol} {dir_text}"

        content_lines = [
            f"**价格**: ${price:,.2f}",
            f"**综合评分**: {score:+.4f}",
            f"**方向**: {direction}",
            "",
            "**各因子信号**:",
        ]

        factor_names_cn = {
            "MA排列": "MA排列",
            "ADX强度": "ADX强度",
            "SuperTrend": "SuperTrend",
            "MACD动量": "MACD动量",
            "OBV能量潮": "OBV能量潮",
            "RSI背离": "RSI背离",
            "布林带": "布林带",
            "成交量突破": "成交量突破",
            "ATR突破": "ATR突破",
        }

        signal_emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}

        for factor_name, detail in details.items():
            cn_name = factor_names_cn.get(factor_name, factor_name)
            factor_scores = analysis_result.get("factor_scores", {})
            s = factor_scores.get(factor_name, 0)
            sig = "BUY" if s > 0.1 else ("SELL" if s < -0.1 else "HOLD")
            emoji = signal_emoji.get(sig, "⚪")
            content_lines.append(f"{emoji} **{cn_name}**: {detail}")

        content = "\n".join(content_lines)

        return self.send_message(title, content, score, direction)

    def send_daily_report(self, all_scores, tickers):
        """发送每日报告"""
        title = f"📊 CryptoTracker 每日策略报告"

        content_lines = [f"**报告时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]

        for symbol, score_data in all_scores.items():
            display = symbol.replace("USDT", "")
            direction = score_data.get("direction", "HOLD")
            total = score_data.get("total_score", 0)
            price = score_data.get("price", 0)

            emoji_map = {
                "STRONG_BUY": "🟢🟢",
                "BUY": "🟢",
                "HOLD": "🟡",
                "SELL": "🟠",
                "STRONG_SELL": "🔴🔴",
            }
            emoji = emoji_map.get(direction, "⚪")

            ticker_info = tickers.get(symbol, {})
            change = ticker_info.get("change_pct", 0)

            content_lines.append(
                f"{emoji} **{display}/USDT**: ${price:,.2f} ({change:+.2f}%) | "
                f"评分: {total:+.3f} | {direction}"
            )

        content_lines.append("")
        content_lines.append("⚠️ *以上为策略信号参考，不构成投资建议*")

        content = "\n".join(content_lines)
        return self.send_message(title, content)
