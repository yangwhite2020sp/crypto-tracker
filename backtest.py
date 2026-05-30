"""
CryptoTracker Pro - 回测引擎
验证策略在历史数据上的表现
"""
import pandas as pd
import numpy as np
from strategies.spot_strategies import CompositeScoringSystem
from config import BACKTEST_DEFAULT_CAPITAL, BACKTEST_FEE_RATE


class BacktestEngine:
    """回测引擎"""

    def __init__(self, initial_capital=BACKTEST_DEFAULT_CAPITAL, fee_rate=BACKTEST_FEE_RATE):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.scoring = CompositeScoringSystem()

    def run(self, df, score_threshold=0.1, stop_loss_pct=0.05):
        """
        运行简单回测
        信号买入/卖出，固定止损

        参数:
            df: DataFrame with OHLCV data
            score_threshold: 买入信号阈值
            stop_loss_pct: 止损比例

        返回:
            dict with performance metrics
        """
        if df is None or len(df) < 100:
            return {"error": "数据不足"}

        # 使用前半数据预热指标，后半数据回试
        warmup = 100
        test_df = df.iloc[warmup:].copy().reset_index(drop=True)

        capital = self.initial_capital
        position = 0  # 持仓数量
        entry_price = 0
        trades = []
        equity_curve = [capital]
        wins = 0
        losses = 0

        # 滑动窗口分析
        window_size = 60

        for i in range(window_size, len(test_df)):
            window = test_df.iloc[i - window_size: i + 1].copy()
            current_price = test_df.iloc[i]["close"]

            try:
                # 获取信号
                result = self.scoring.analyze(window)
                score = result["total_score"]
                direction = result["direction"]
            except Exception:
                equity_curve.append(capital + position * current_price)
                continue

            # 止损检查
            if position > 0 and entry_price > 0:
                loss_pct = (current_price - entry_price) / entry_price
                if loss_pct <= -stop_loss_pct:
                    # 止损卖出
                    sell_value = position * current_price * (1 - self.fee_rate)
                    pnl = sell_value - position * entry_price
                    trades.append({
                        "type": "STOP_LOSS",
                        "entry": entry_price,
                        "exit": current_price,
                        "pnl": pnl,
                        "pnl_pct": loss_pct * 100,
                    })
                    capital += position * current_price * (1 - self.fee_rate)
                    position = 0
                    entry_price = 0
                    losses += 1
                    equity_curve.append(capital)
                    continue

            # 买入信号
            if position == 0 and (direction in ["BUY", "STRONG_BUY"]) and score > score_threshold:
                position = (capital * 0.95) / current_price  # 95%仓位
                entry_price = current_price
                capital -= position * current_price * (1 + self.fee_rate)
                trades.append({
                    "type": "BUY",
                    "price": current_price,
                    "score": score,
                    "direction": direction,
                })

            # 卖出信号
            elif position > 0 and (direction in ["SELL", "STRONG_SELL"]) and score < -score_threshold:
                sell_value = position * current_price * (1 - self.fee_rate)
                pnl = sell_value - position * entry_price
                pnl_pct = (current_price / entry_price - 1) * 100

                trades.append({
                    "type": "SELL",
                    "entry": entry_price,
                    "exit": current_price,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "score": score,
                })

                if pnl > 0:
                    wins += 1
                else:
                    losses += 1

                capital += position * current_price * (1 - self.fee_rate)
                position = 0
                entry_price = 0

            # 记录净值
            total_equity = capital + position * current_price
            equity_curve.append(total_equity)

        # 如果还有持仓，按最后价格平仓
        final_price = test_df.iloc[-1]["close"]
        if position > 0:
            capital += position * final_price * (1 - self.fee_rate)
            pnl = position * final_price - position * entry_price
            trades.append({
                "type": "FINAL_CLOSE",
                "entry": entry_price,
                "exit": final_price,
                "pnl": pnl,
                "pnl_pct": (final_price / entry_price - 1) * 100,
            })
            position = 0

        # 计算绩效指标
        total_trades = wins + losses
        win_rate = wins / total_trades * 100 if total_trades > 0 else 0
        total_pnl = capital - self.initial_capital
        total_return = (capital / self.initial_capital - 1) * 100

        # 最大回撤
        equity = pd.Series(equity_curve)
        rolling_max = equity.cummax()
        drawdown = (equity - rolling_max) / rolling_max * 100
        max_drawdown = drawdown.min()

        # 盈亏比
        trade_pnls = [t.get("pnl", 0) for t in trades if t["type"] in ["SELL", "STOP_LOSS", "FINAL_CLOSE"]]
        avg_win = np.mean([p for p in trade_pnls if p > 0]) if any(p > 0 for p in trade_pnls) else 0
        avg_loss = abs(np.mean([p for p in trade_pnls if p < 0])) if any(p < 0 for p in trade_pnls) else 1
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0

        # 买入持有对比
        buy_hold_return = (final_price / test_df.iloc[window_size]["close"] - 1) * 100

        result = {
            "initial_capital": self.initial_capital,
            "final_capital": round(capital, 2),
            "total_pnl": round(total_pnl, 2),
            "total_return": round(total_return, 2),
            "buy_hold_return": round(buy_hold_return, 2),
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "max_drawdown": round(max_drawdown, 2),
            "profit_factor": round(profit_factor, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "equity_curve": equity_curve,
            "trades": trades[-20:],  # 最近20笔
            "trade_count": len(trades),
            "score_threshold": score_threshold,
            "stop_loss_pct": stop_loss_pct * 100,
        }

        return result

    def optimize_threshold(self, df, thresholds=[0.05, 0.1, 0.15, 0.2, 0.25, 0.3]):
        """优化信号阈值"""
        results = []
        for threshold in thresholds:
            result = self.run(df, score_threshold=threshold)
            if "error" not in result:
                results.append({
                    "threshold": threshold,
                    "total_return": result["total_return"],
                    "win_rate": result["win_rate"],
                    "max_drawdown": result["max_drawdown"],
                    "total_trades": result["total_trades"],
                    "profit_factor": result["profit_factor"],
                })

        if results:
            results.sort(key=lambda x: x["total_return"], reverse=True)
            return results
        return []
