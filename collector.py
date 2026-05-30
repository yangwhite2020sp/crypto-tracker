"""
CryptoTracker Pro - 行情数据采集模块
使用 Binance 免费 API（无需 Key）
"""
import time
import requests
import pandas as pd
from config import BINANCE_BASE_URL, SYMBOLS, INTERVALS, KLINE_LIMIT, HTTP_PROXY, HTTPS_PROXY, USE_PROXY
from database import save_klines, get_klines

# 代理配置
PROXIES = {}
if USE_PROXY:
    PROXIES = {"http": HTTP_PROXY, "https": HTTPS_PROXY}


class BinanceCollector:
    def __init__(self):
        self.base_url = BINANCE_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "CryptoTracker/1.0"})
        if PROXIES:
            self.session.proxies.update(PROXIES)

    def _request(self, endpoint, params=None, retries=3):
        """带重试的请求"""
        url = f"{self.base_url}{endpoint}"
        for attempt in range(retries):
            try:
                resp = self.session.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    wait = 30 * (attempt + 1)
                    print(f"[Collector] 限流，等待 {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"[Collector] HTTP {resp.status_code}: {resp.text[:200]}")
            except requests.exceptions.RequestException as e:
                print(f"[Collector] 请求失败 (attempt {attempt+1}): {e}")
                if attempt < retries - 1:
                    time.sleep(5)
        return None

    def get_klines(self, symbol, interval, limit=KLINE_LIMIT):
        """获取K线数据"""
        data = self._request("/api/v3/klines", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        })
        return data

    def get_ticker_24h(self, symbol):
        """获取24小时行情"""
        data = self._request("/api/v3/ticker/24hr", {"symbol": symbol})
        return data

    def get_order_book(self, symbol, limit=20):
        """获取订单簿"""
        data = self._request("/api/v3/depth", {"symbol": symbol, "limit": limit})
        return data

    def get_exchange_info(self):
        """获取交易对信息"""
        data = self._request("/api/v3/exchangeInfo")
        return data

    def collect_all(self):
        """采集所有币种所有时间框架的数据"""
        results = {}
        for symbol in SYMBOLS:
            results[symbol] = {}
            for name, interval in INTERVALS.items():
                print(f"[Collector] 采集 {symbol} {interval}...")
                data = self.get_klines(symbol, interval)
                if data:
                    count = save_klines(symbol, interval, data)
                    results[symbol][name] = count
                    print(f"[Collector] {symbol} {interval}: 保存 {count} 条")
                else:
                    results[symbol][name] = 0
                    print(f"[Collector] {symbol} {interval}: 采集失败")
                time.sleep(0.5)  # 避免限流
        return results

    def get_all_tickers(self):
        """获取所有追踪币种的24小时行情"""
        tickers = {}
        for symbol in SYMBOLS:
            data = self.get_ticker_24h(symbol)
            if data:
                tickers[symbol] = {
                    "price": float(data["lastPrice"]),
                    "change_pct": float(data["priceChangePercent"]),
                    "high": float(data["highPrice"]),
                    "low": float(data["lowPrice"]),
                    "volume": float(data["volume"]),
                    "quote_volume": float(data["quoteVolume"]),
                }
            time.sleep(0.3)
        return tickers


class CoinGeckoCollector:
    """CoinGecko 备用数据源"""

    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        self.session = requests.Session()

    def get_ohlc(self, coin_id, days=180, vs_currency="usd"):
        """获取OHLC数据"""
        try:
            resp = self.session.get(
                f"{self.base_url}/coins/{coin_id}/ohlc",
                params={"vs_currency": vs_currency, "days": days},
                timeout=15
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"[CoinGecko] 请求失败: {e}")
        return None


# 便捷函数
def collect_once():
    """执行一次完整采集"""
    collector = BinanceCollector()
    return collector.collect_all()


def get_tickers():
    """获取所有行情"""
    collector = BinanceCollector()
    return collector.get_all_tickers()


if __name__ == "__main__":
    print("=== 测试数据采集 ===")
    collector = BinanceCollector()

    # 测试采集
    results = collector.collect_all()
    print(f"\n采集结果: {results}")

    # 测试行情
    tickers = collector.get_all_tickers()
    for sym, t in tickers.items():
        print(f"{sym}: ${t['price']:,.2f} ({t['change_pct']:+.2f}%)")
