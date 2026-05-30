"""
CryptoTracker Pro - 定时任务调度
"""
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from config import SYMBOLS, DATA_UPDATE_INTERVAL, SIGNAL_CHECK_INTERVAL, DAILY_REPORT_HOUR
from collector import BinanceCollector
from database import init_db, save_composite_score, save_alert, get_klines
from strategies.spot_strategies import CompositeScoringSystem
from notifier import Notifier


class TrackerScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.collector = BinanceCollector()
        self.scoring = CompositeScoringSystem()
        self.notifier = Notifier()

    def start(self):
        """启动调度器"""
        # 数据采集：每15分钟
        self.scheduler.add_job(
            self.collect_data,
            "interval",
            minutes=DATA_UPDATE_INTERVAL,
            id="data_collection",
            name="行情数据采集",
        )

        # 策略分析：每60分钟
        self.scheduler.add_job(
            self.analyze_signals,
            "interval",
            minutes=SIGNAL_CHECK_INTERVAL,
            id="signal_analysis",
            name="策略信号分析",
        )

        # 每日报告：每天早上9点
        self.scheduler.add_job(
            self.daily_report,
            "cron",
            hour=DAILY_REPORT_HOUR,
            minute=0,
            id="daily_report",
            name="每日策略报告",
        )

        self.scheduler.start()
        print(f"[Scheduler] 调度器已启动")
        print(f"  - 数据采集: 每 {DATA_UPDATE_INTERVAL} 分钟")
        print(f"  - 策略分析: 每 {SIGNAL_CHECK_INTERVAL} 分钟")
        print(f"  - 每日报告: 每天 {DAILY_REPORT_HOUR}:00")

    def stop(self):
        self.scheduler.shutdown()
        print("[Scheduler] 调度器已停止")

    def collect_data(self):
        """采集数据"""
        print(f"[{datetime.now().strftime('%H:%M')}] 开始采集数据...")
        try:
            results = self.collector.collect_all()
            total = sum(
                sum(v.values()) if isinstance(v, dict) else v
                for v in results.values()
            )
            print(f"  采集完成: {total} 条数据")
        except Exception as e:
            print(f"  采集失败: {e}")

    def analyze_signals(self):
        """分析策略信号"""
        print(f"[{datetime.now().strftime('%H:%M')}] 开始策略分析...")
        try:
            for symbol in SYMBOLS:
                df = get_klines(symbol, "1d", 100)
                if df.empty:
                    continue

                result = self.scoring.analyze(df, symbol)
                price = result["price"]
                score = result["total_score"]
                direction = result["direction"]

                # 保存评分
                save_composite_score(
                    symbol, "daily", score, direction,
                    result["confidence"], result["factor_scores"], price
                )

                # 强信号触发告警
                if direction in ["STRONG_BUY", "STRONG_SELL"]:
                    save_alert(symbol, "STRONG_SIGNAL",
                               f"{direction} 评分:{score:+.3f}", score, price)
                    self.notifier.send_signal_alert(symbol, result)
                    print(f"  {symbol}: {direction} (评分: {score:+.3f}) 🔔 已推送")
                else:
                    print(f"  {symbol}: {direction} (评分: {score:+.3f})")

        except Exception as e:
            print(f"  分析失败: {e}")

    def daily_report(self):
        """每日报告"""
        print(f"[{datetime.now().strftime('%H:%M')}] 生成每日报告...")
        try:
            from collector import get_tickers
            tickers = get_tickers()
            all_scores = {}

            for symbol in SYMBOLS:
                df = get_klines(symbol, "1d", 100)
                if not df.empty:
                    result = self.scoring.analyze(df, symbol)
                    all_scores[symbol] = result

            self.notifier.send_daily_report(all_scores, tickers)
            print("  每日报告已发送")
        except Exception as e:
            print(f"  报告失败: {e}")
