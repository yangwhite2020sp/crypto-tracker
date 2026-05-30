"""
CryptoTracker Pro - 配置文件
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ============ 基础配置 ============
DEBUG = True
SECRET_KEY = os.getenv("SECRET_KEY", "crypto-tracker-secret-key")
PORT = int(os.getenv("PORT", 5000))

# ============ 追踪的币种 ============
SYMBOLS = ["BTCUSDT", "BNBUSDT", "ETHUSDT"]
SYMBOL_DISPLAY = {
    "BTCUSDT": "BTC",
    "BNBUSDT": "BNB",
    "ETHUSDT": "ETH",
}

# ============ 数据源配置 ============
BINANCE_BASE_URL = "https://api.binance.com"
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

# ============ 时间框架 ============
INTERVALS = {
    "weekly": "1w",    # 周线 - 大方向
    "daily": "1d",     # 日线 - 主信号
    "4h": "4h",        # 4小时 - 精确入场
}
# K线历史数量
KLINE_LIMIT = 200

# ============ 数据库 ============
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "data", "crypto.db")

# ============ 策略参数 ============
STRATEGY_PARAMS = {
    # MA
    "ma_short": 7,
    "ma_mid": 25,
    "ma_long": 99,
    # RSI
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    # MACD
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    # 布林带
    "bb_period": 20,
    "bb_std": 2.0,
    # ATR
    "atr_period": 14,
    "atr_multiplier": 2.0,
    # ADX
    "adx_period": 14,
    "adx_threshold": 25,
    # SuperTrend
    "st_period": 10,
    "st_multiplier": 3.0,
    # KDJ
    "kdj_period": 9,
    # OBV
    "obv_ma": 20,
    # 成交量
    "volume_ma": 20,
    "volume_spike_ratio": 2.0,
    # 背离检测回看
    "divergence_lookback": 20,
}

# ============ 多因子评分权重 ============
FACTOR_WEIGHTS = {
    # 趋势层 (40%)
    "ma_alignment": 0.15,
    "adx_strength": 0.10,
    "supertrend": 0.15,
    # 动量层 (20%)
    "macd_momentum": 0.12,
    "obv_trend": 0.08,
    # 震荡层 (20%)
    "rsi_divergence": 0.12,
    "bollinger_position": 0.08,
    # 量价层 (20%)
    "volume_breakout": 0.10,
    "atr_breakout": 0.10,
}

# ============ 通知配置 ============
# 飞书 Webhook
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")
# 企业微信 Webhook
WECHAT_WEBHOOK = os.getenv("WECHAT_WEBHOOK", "")

# ============ 定时任务 ============
# 数据更新时间间隔（分钟）
DATA_UPDATE_INTERVAL = 15
# 策略信号检查间隔（分钟）
SIGNAL_CHECK_INTERVAL = 60
# 每日报告时间（小时，24小时制）
DAILY_REPORT_HOUR = 8

# ============ 代理配置 ============
# 通过环境变量 HTTPS_PROXY / HTTP_PROXY 设置代理
# 例如: export HTTPS_PROXY=http://127.0.0.1:7890
USE_PROXY = os.getenv("USE_PROXY", "false").lower() in ("true", "1", "yes")
BACKTEST_DEFAULT_CAPITAL = 10000  # USDT
BACKTEST_FEE_RATE = 0.001         # 0.1% 手续费
