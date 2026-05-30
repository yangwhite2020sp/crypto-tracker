"""
CryptoTracker Pro - Flask Web 主应用
"""
import json
import os
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from config import SYMBOLS, SYMBOL_DISPLAY, INTERVALS, FACTOR_WEIGHTS
from database import init_db, get_klines, get_latest_composite_scores, get_data_status, get_latest_signals
from collector import BinanceCollector, get_tickers
from strategies.spot_strategies import CompositeScoringSystem
from backtest import BacktestEngine
from notifier import Notifier
from scheduler import TrackerScheduler

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "crypto-tracker")

# 全局
scoring = CompositeScoringSystem()
scheduler = TrackerScheduler()

# 缓存 ticker 数据，避免每次请求都调 API
_ticker_cache = {}
_ticker_cache_time = 0
_TICKER_CACHE_TTL = 60  # 60秒缓存

def get_cached_tickers():
    global _ticker_cache, _ticker_cache_time
    now = datetime.now().timestamp()
    if now - _ticker_cache_time > _TICKER_CACHE_TTL or not _ticker_cache:
        try:
            _ticker_cache = get_tickers()
            _ticker_cache_time = now
        except Exception:
            pass
    return _ticker_cache


@app.context_processor
def inject_globals():
    return {
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "SYMBOLS": SYMBOLS,
        "SYMBOL_DISPLAY": SYMBOL_DISPLAY,
    }


@app.route("/")
def index():
    """仪表盘主页"""
    tickers = get_cached_tickers()
    data_status = get_data_status()

    # 获取每个币种的最新评分
    scores = {}
    for symbol in SYMBOLS:
        df = get_klines(symbol, "1d", 100)
        if not df.empty:
            result = scoring.analyze(df, symbol)
            scores[symbol] = result

    return render_template("index.html", tickers=tickers, scores=scores, data_status=data_status)


@app.route("/chart/<symbol>")
def chart(symbol):
    """图表页"""
    interval = request.args.get("interval", "daily")
    interval_map = {"weekly": "1w", "daily": "1d", "4h": "4h"}
    binance_interval = interval_map.get(interval, "1d")

    df = get_klines(symbol, binance_interval, 200)
    signals_df = get_latest_signals(symbol, 30)

    analysis = None
    if not df.empty:
        analysis = scoring.analyze(df, symbol)

    return render_template(
        "chart.html",
        symbol=symbol,
        display=SYMBOL_DISPLAY.get(symbol, symbol),
        interval=interval,
        analysis=analysis,
        signals=signals_df.to_dict("records") if not signals_df.empty else [],
    )


@app.route("/strategies")
def strategies():
    """策略信号页"""
    all_analysis = {}
    for symbol in SYMBOLS:
        df = get_klines(symbol, "1d", 100)
        if not df.empty:
            all_analysis[symbol] = scoring.analyze(df, symbol)

    return render_template("strategies.html", analysis=all_analysis)


@app.route("/backtest/<symbol>")
def backtest_page(symbol):
    """回测页"""
    interval = request.args.get("interval", "daily")
    threshold = float(request.args.get("threshold", 0.1))
    stop_loss = float(request.args.get("sl", 5.0)) / 100

    df = get_klines(symbol, "1d", 500)
    result = None
    optimization = []

    if not df.empty:
        engine = BacktestEngine()
        result = engine.run(df, score_threshold=threshold, stop_loss_pct=stop_loss)
        optimization = engine.optimize_threshold(df)

    return render_template(
        "backtest.html",
        symbol=symbol,
        display=SYMBOL_DISPLAY.get(symbol, symbol),
        result=result,
        optimization=optimization,
        threshold=threshold,
    )


# ============ API 路由 ============

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """刷新数据"""
    from collector import collect_once
    results = collect_once()
    return jsonify({"success": True, "results": results})


@app.route("/api/analyze/<symbol>")
def api_analyze(symbol):
    """分析单个币种"""
    result = {}
    for tf_name, interval in [("daily", "1d"), ("weekly", "1w"), ("4h", "4h")]:
        df = get_klines(symbol, interval, 200)
        if not df.empty:
            result[tf_name] = scoring.analyze(df, symbol)

    return jsonify(result)


@app.route("/api/backtest/<symbol>")
def api_backtest(symbol):
    """回测 API"""
    threshold = float(request.args.get("threshold", 0.1))
    stop_loss = float(request.args.get("sl", 5.0)) / 100

    df = get_klines(symbol, "1d", 500)
    if df.empty:
        return jsonify({"error": "无数据"})

    engine = BacktestEngine()
    result = engine.run(df, score_threshold=threshold, stop_loss_pct=stop_loss)

    # 移除不可序列化的数据
    result.pop("equity_curve", None)
    return jsonify(result)


@app.route("/api/klines/<symbol>")
def api_klines(symbol):
    """获取K线数据（图表用）"""
    interval = request.args.get("interval", "1d")
    df = get_klines(symbol, interval, 200)

    if df.empty:
        return jsonify({"error": "无数据"})

    data = {
        "times": df["open_time"].dt.strftime("%Y-%m-%d").tolist(),
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
        "volume": df["volume"].tolist(),
    }
    return jsonify(data)


if __name__ == "__main__":
    init_db()
    # 启动定时任务调度器
    scheduler.start()
    # 首次启动先采集一次数据
    try:
        from collector import collect_once
        t = threading.Thread(target=collect_once, daemon=True)
        t.start()
    except Exception:
        pass
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
