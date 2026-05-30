"""
CryptoTracker Pro - 现货交易策略实现

8大因子 + 综合评分系统

趋势层: MA排列, ADX强度, SuperTrend
动量层: MACD柱状图, OBV能量潮
震荡层: RSI背离, 布林带位置
量价层: 成交量突破, ATR突破
"""
import pandas as pd
import numpy as np
from strategies.base import BaseStrategy
from config import STRATEGY_PARAMS as P
import ta


# ============================================================
# 趋势层 (40%)
# ============================================================

class MAAlignmentStrategy(BaseStrategy):
    """
    MA多均线排列策略 (权重 15%)
    MA7/MA25/MA99 多头排列=买入, 空头排列=卖出
    """

    def __init__(self):
        super().__init__("MA排列", P.get("ma_alignment", 0.15))

    def analyze(self, df):
        if not self.validate_df(df, P["ma_long"] + 10):
            return self._neutral("数据不足")

        close = df["close"]
        ma_short = ta.trend.sma_indicator(close, P["ma_short"])
        ma_mid = ta.trend.sma_indicator(close, P["ma_mid"])
        ma_long = ta.trend.sma_indicator(close, P["ma_long"])

        s = ma_short.iloc[-1]
        m = ma_mid.iloc[-1]
        l = ma_long.iloc[-1]
        price = close.iloc[-1]

        # 多头排列
        if s > m > l:
            strength = min((s - l) / l * 100, 3) / 3  # 归一化强度
            score = self.safe_score(0.3 + 0.7 * strength)
            return {
                "signal": "BUY",
                "score": score,
                "details": f"多头排列: MA{P['ma_short']}({s:.0f})>MA{P['ma_mid']}({m:.0f})>MA{P['ma_long']}({l:.0f})",
                "raw": {"ma_short": s, "ma_mid": m, "ma_long": l, "alignment": "bullish"},
            }
        # 空头排列
        elif s < m < l:
            strength = min((l - s) / l * 100, 3) / 3
            score = self.safe_score(-0.3 - 0.7 * strength)
            return {
                "signal": "SELL",
                "score": score,
                "details": f"空头排列: MA{P['ma_short']}({s:.0f})<MA{P['ma_mid']}({m:.0f})<MA{P['ma_long']}({l:.0f})",
                "raw": {"ma_short": s, "ma_mid": m, "ma_long": l, "alignment": "bearish"},
            }
        # 混合状态
        else:
            # 偏多还是偏空
            if s > m:
                score = 0.15
                detail = f"偏多过渡: MA{P['ma_short']}>MA{P['ma_mid']}, 但MA{P['ma_long']}未确认"
            else:
                score = -0.15
                detail = f"偏空过渡: MA{P['ma_short']}<MA{P['ma_mid']}, 但MA{P['ma_long']}未确认"
            return {
                "signal": "HOLD",
                "score": score,
                "details": detail,
                "raw": {"ma_short": s, "ma_mid": m, "ma_long": l, "alignment": "mixed"},
            }

    def _neutral(self, reason):
        return {"signal": "HOLD", "score": 0, "details": reason, "raw": {}}


class ADXStrengthStrategy(BaseStrategy):
    """
    ADX趋势强度策略 (权重 10%)
    ADX>25 有趋势, ADX<20 震荡
    配合 +DI/-DI 方向
    """

    def __init__(self):
        super().__init__("ADX强度", P.get("adx_strength", 0.10))

    def analyze(self, df):
        if not self.validate_df(df, P["adx_period"] + 20):
            return {"signal": "HOLD", "score": 0, "details": "数据不足", "raw": {}}

        adx = ta.trend.adx(
            df["high"], df["low"], df["close"], P["adx_period"]
        )
        di_pos = ta.trend.adx_pos(
            df["high"], df["low"], df["close"], P["adx_period"]
        )
        di_neg = ta.trend.adx_neg(
            df["high"], df["low"], df["close"], P["adx_period"]
        )

        if adx.isna().iloc[-1]:
            return {"signal": "HOLD", "score": 0, "details": "ADX数据不足", "raw": {}}

        val = adx.iloc[-1]
        pos = di_pos.iloc[-1]
        neg = di_neg.iloc[-1]

        if val >= P["adx_threshold"]:
            if pos > neg:
                score = self.safe_score(0.5 + (val - 25) / 50)
                signal = "BUY"
                detail = f"强趋势(+DI>-DI) ADX={val:.1f}, 强度:+{val:.0f}"
            else:
                score = self.safe_score(-0.5 - (val - 25) / 50)
                signal = "SELL"
                detail = f"强趋势(+DI<-DI) ADX={val:.1f}, 强度:-{val:.0f}"
        elif val >= 20:
            score = 0.1 if pos > neg else -0.1
            signal = "HOLD"
            detail = f"趋势酝酿中 ADX={val:.1f}"
        else:
            score = 0
            signal = "HOLD"
            detail = f"震荡市 ADX={val:.1f}<20, 趋势策略暂停"

        return {
            "signal": signal,
            "score": score,
            "details": detail,
            "raw": {"adx": val, "di_plus": pos, "di_minus": neg},
        }


class SuperTrendStrategy(BaseStrategy):
    """
    SuperTrend策略 (权重 15%)
    基于 ATR 的趋势跟踪指标
    """

    def __init__(self):
        super().__init__("SuperTrend", P.get("supertrend", 0.15))

    def analyze(self, df):
        if not self.validate_df(df, P["st_period"] + 10):
            return {"signal": "HOLD", "score": 0, "details": "数据不足", "raw": {}}

        st_period = P["st_period"]
        st_mult = P["st_multiplier"]

        # 计算 SuperTrend
        hl2 = (df["high"] + df["low"]) / 2
        atr = ta.volatility.average_true_range(df["high"], df["low"], df["close"], st_period)

        upper_band = hl2 + st_mult * atr
        lower_band = hl2 - st_mult * atr

        supertrend = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)

        supertrend.iloc[0] = upper_band.iloc[0]
        direction.iloc[0] = -1

        for i in range(1, len(df)):
            # 上轨
            if upper_band.iloc[i] < upper_band.iloc[i - 1] or df["close"].iloc[i - 1] > upper_band.iloc[i - 1]:
                upper_band.iloc[i] = upper_band.iloc[i]
            else:
                upper_band.iloc[i] = upper_band.iloc[i - 1]

            # 下轨
            if lower_band.iloc[i] > lower_band.iloc[i - 1] or df["close"].iloc[i - 1] < lower_band.iloc[i - 1]:
                lower_band.iloc[i] = lower_band.iloc[i]
            else:
                lower_band.iloc[i] = lower_band.iloc[i - 1]

            # 方向
            if df["close"].iloc[i] > upper_band.iloc[i - 1]:
                direction.iloc[i] = 1
                supertrend.iloc[i] = lower_band.iloc[i]
            elif df["close"].iloc[i] < lower_band.iloc[i - 1]:
                direction.iloc[i] = -1
                supertrend.iloc[i] = upper_band.iloc[i]
            else:
                direction.iloc[i] = direction.iloc[i - 1]
                supertrend.iloc[i] = lower_band.iloc[i] if direction.iloc[i] == 1 else upper_band.iloc[i]

        curr_dir = direction.iloc[-1]
        prev_dir = direction.iloc[-2] if len(direction) > 1 else curr_dir
        price = df["close"].iloc[-1]
        st_value = supertrend.iloc[-1]

        if curr_dir == 1:
            if prev_dir == -1:
                signal = "BUY"
                score = 0.8
                detail = f"SuperTrend翻多(${st_value:,.0f}), 金叉!"
            else:
                signal = "BUY"
                score = 0.5
                detail = f"SuperTrend多头运行中, 支撑:${st_value:,.0f}"
        else:
            if prev_dir == 1:
                signal = "SELL"
                score = -0.8
                detail = f"SuperTrend翻空(${st_value:,.0f}), 死叉!"
            else:
                signal = "SELL"
                score = -0.5
                detail = f"SuperTrend空头运行中, 压力:${st_value:,.0f}"

        return {
            "signal": signal,
            "score": score,
            "details": detail,
            "raw": {"supertrend": st_value, "direction": curr_dir},
        }


# ============================================================
# 动量层 (20%)
# ============================================================

class MACDMomentumStrategy(BaseStrategy):
    """
    MACD柱状图动量策略 (权重 12%)
    金叉死叉 + 柱状图动能变化
    """

    def __init__(self):
        super().__init__("MACD动量", P.get("macd_momentum", 0.12))

    def analyze(self, df):
        if not self.validate_df(df, P["macd_slow"] + P["macd_signal"] + 10):
            return {"signal": "HOLD", "score": 0, "details": "数据不足", "raw": {}}

        macd = ta.trend.MACD(df["close"], P["macd_fast"], P["macd_slow"], P["macd_signal"])
        macd_line = macd.macd()
        signal_line = macd.macd_signal()
        histogram = macd.macd_diff()

        m = macd_line.iloc[-1]
        s = signal_line.iloc[-1]
        h = histogram.iloc[-1]
        h_prev = histogram.iloc[-2]

        # 金叉 + 柱状图扩大
        if m > s:
            if h > h_prev:
                score = self.safe_score(0.6 + min(abs(h) / abs(m) * 2, 0.4))
                detail = f"MACD金叉+动能增强, 柱状图:{h:.2f}->{h:.2f}(扩大)"
            else:
                score = 0.3
                detail = f"MACD金叉但动能减弱, 柱状图:{h:.2f}->{h:.2f}(收缩)"
            signal = "BUY"
        # 死叉 + 柱状图扩大
        elif m < s:
            if h < h_prev:
                score = self.safe_score(-0.6 - min(abs(h) / abs(m) * 2, 0.4))
                detail = f"MACD死叉+动能增强, 柱状图:{h:.2f}->{h:.2f}(扩大)"
            else:
                score = -0.3
                detail = f"MACD死叉但动能减弱, 柱状图:{h:.2f}->{h:.2f}(收缩)"
            signal = "SELL"
        else:
            score = 0
            signal = "HOLD"
            detail = "MACD中性"

        return {
            "signal": signal,
            "score": score,
            "details": detail,
            "raw": {"macd": m, "signal": s, "histogram": h, "hist_prev": h_prev},
        }


class OBVTrendStrategy(BaseStrategy):
    """
    OBV能量潮策略 (权重 8%)
    OBV方向和与价格的关系
    """

    def __init__(self):
        super().__init__("OBV能量潮", P.get("obv_trend", 0.08))

    def analyze(self, df):
        if not self.validate_df(df, P["obv_ma"] + 20):
            return {"signal": "HOLD", "score": 0, "details": "数据不足", "raw": {}}

        obv = ta.volume.on_balance_volume(df["close"], df["volume"])
        obv_ma = obv.rolling(P["obv_ma"]).mean()

        curr_obv = obv.iloc[-1]
        curr_ma = obv_ma.iloc[-1]

        # 价格趋势（近10日）
        price_change_10 = (df["close"].iloc[-1] / df["close"].iloc[-11] - 1) * 100 if len(df) > 10 else 0
        obv_change_10 = (obv.iloc[-1] / obv.iloc[-11] - 1) * 100 if len(df) > 10 else 0

        if pd.isna(curr_ma):
            return {"signal": "HOLD", "score": 0, "details": "OBV数据不足", "raw": {}}

        # OBV > MA = 资金流入
        if curr_obv > curr_ma:
            score = self.safe_score(0.3 + min(obv_change_10 / 10, 0.4))
            detail = f"OBV(${curr_obv:,.0f})>MA(${curr_ma:,.0f}), 资金流入, 10日变化:{obv_change_10:+.1f}%"
        else:
            score = self.safe_score(-0.3 - min(abs(obv_change_10) / 10, 0.4))
            detail = f"OBV(${curr_obv:,.0f})<MA(${curr_ma:,.0f}), 资金流出, 10日变化:{obv_change_10:+.1f}%"

        # 背离检测
        if price_change_10 > 2 and obv_change_10 < -1:
            score = min(score, -0.3)
            detail += " [警告:顶背离!价格上涨但OBV下降]"
        elif price_change_10 < -2 and obv_change_10 > 1:
            score = max(score, 0.3)
            detail += " [提示:底背离!价格下跌但OBV上升]"

        signal = "BUY" if score > 0.1 else ("SELL" if score < -0.1 else "HOLD")

        return {
            "signal": signal,
            "score": score,
            "details": detail,
            "raw": {"obv": curr_obv, "obv_ma": curr_ma},
        }


# ============================================================
# 震荡层 (20%)
# ============================================================

class RSIDivergenceStrategy(BaseStrategy):
    """
    RSI背离策略 (权重 12%)
    普通RSI超买超卖 + 背离检测
    """

    def __init__(self):
        super().__init__("RSI背离", P.get("rsi_divergence", 0.12))

    def analyze(self, df):
        if not self.validate_df(df, P["rsi_period"] + P["divergence_lookback"]):
            return {"signal": "HOLD", "score": 0, "details": "数据不足", "raw": {}}

        rsi = ta.momentum.rsi(df["close"], P["rsi_period"])
        curr_rsi = rsi.iloc[-1]

        lookback = P["divergence_lookback"]
        price_lows = df["close"].rolling(5, center=True).min()
        price_highs = df["close"].rolling(5, center=True).max()
        rsi_lows = rsi.rolling(5, center=True).min()
        rsi_highs = rsi.rolling(5, center=True).max()

        # 找最近两个低点
        recent_window = df.iloc[-lookback:]
        recent_rsi = rsi.iloc[-lookback:]

        # 简单背离检测
        divergence_signal = None
        if len(df) > lookback:
            half = lookback // 2
            price_first_half = df["close"].iloc[-lookback:-half].min()
            price_second_half = df["close"].iloc[-half:].min()
            rsi_first_half = rsi.iloc[-lookback:-half].min()
            rsi_second_half = rsi.iloc[-half:].min()

            # 底背离: 价格新低, RSI不创新低
            if price_second_half < price_first_half and rsi_second_half > rsi_first_half:
                divergence_signal = "bullish_divergence"

            # 顶背离: 价格新高, RSI不创新高
            price_first_high = df["close"].iloc[-lookback:-half].max()
            price_second_high = df["close"].iloc[-half:].max()
            rsi_first_high = rsi.iloc[-lookback:-half].max()
            rsi_second_high = rsi.iloc[-half:].max()

            if price_second_high > price_first_high and rsi_second_high < rsi_first_high:
                divergence_signal = "bearish_divergence"

        # 综合评分
        if divergence_signal == "bullish_divergence":
            score = 0.8
            signal = "BUY"
            detail = f"RSI底背离! 价格新低但RSI不创新低, 当前RSI={curr_rsi:.1f}"
        elif divergence_signal == "bearish_divergence":
            score = -0.8
            signal = "SELL"
            detail = f"RSI顶背离! 价格新高但RSI不创新高, 当前RSI={curr_rsi:.1f}"
        elif curr_rsi < P["rsi_oversold"]:
            score = self.safe_score(0.6 - (curr_rsi / P["rsi_oversold"]) * 0.3)
            signal = "BUY"
            detail = f"RSI超卖({curr_rsi:.1f}<{P['rsi_oversold']}), 可能反弹"
        elif curr_rsi > P["rsi_overbought"]:
            score = self.safe_score(-0.6 + ((100 - curr_rsi) / (100 - P["rsi_overbought"])) * 0.3)
            signal = "SELL"
            detail = f"RSI超买({curr_rsi:.1f}>{P['rsi_overbought']}), 可能回调"
        else:
            # 中性区域, 看趋势
            if curr_rsi > 55:
                score = 0.15
            elif curr_rsi < 45:
                score = -0.15
            else:
                score = 0
            signal = "HOLD"
            detail = f"RSI中性({curr_rsi:.1f}), 无明确信号"

        return {
            "signal": signal,
            "score": score,
            "details": detail,
            "raw": {"rsi": curr_rsi, "divergence": divergence_signal},
        }


class BollingerPositionStrategy(BaseStrategy):
    """
   布林带位置策略 (权重 8%)
   价格在布林带中的位置 + 带宽变化
    """

    def __init__(self):
        super().__init__("布林带", P.get("bollinger_position", 0.08))

    def analyze(self, df):
        if not self.validate_df(df, P["bb_period"] + 20):
            return {"signal": "HOLD", "score": 0, "details": "数据不足", "raw": {}}

        close = df["close"]
        bb = ta.volatility.BollingerBands(close, P["bb_period"], P["bb_std"])

        upper = bb.bollinger_hband().iloc[-1]
        lower = bb.bollinger_lband().iloc[-1]
        mid = bb.bollinger_mavg().iloc[-1]
        pct_b = bb.bollinger_pband().iloc[-1]  # %B 指标 0~1

        # 带宽 (BandWidth)
        bandwidth = ((upper - lower) / mid) * 100
        bw_ma = bandwidth  # 简化

        price = close.iloc[-1]

        # 位置判断
        if pct_b < 0:
            score = 0.7
            signal = "BUY"
            detail = f"价格突破下轨(%B={pct_b:.2f}), 超卖区, 带宽={bandwidth:.1f}%"
        elif pct_b < 0.2:
            score = 0.4
            signal = "BUY"
            detail = f"价格接近下轨(%B={pct_b:.2f}), 偏低区域"
        elif pct_b > 1:
            score = -0.7
            signal = "SELL"
            detail = f"价格突破上轨(%B={pct_b:.2f}), 超买区, 带宽={bandwidth:.1f}%"
        elif pct_b > 0.8:
            score = -0.4
            signal = "SELL"
            detail = f"价格接近上轨(%B={pct_b:.2f}), 偏高区域"
        else:
            # 在中轨附近
            if pct_b > 0.5:
                score = 0.1
                detail = f"价格在中轨上方(%B={pct_b:.2f}), 中性偏多"
            else:
                score = -0.1
                detail = f"价格在中轨下方(%B={pct_b:.2f}), 中性偏空"
            signal = "HOLD"

        # 带宽收窄提示变盘
        if bandwidth < 5:
            detail += " [带宽极窄, 即将变盘!]"

        return {
            "signal": signal,
            "score": score,
            "details": detail,
            "raw": {"pct_b": pct_b, "upper": upper, "lower": lower, "mid": mid, "bandwidth": bandwidth},
        }


# ============================================================
# 量价层 (20%)
# ============================================================

class VolumeBreakoutStrategy(BaseStrategy):
    """
    成交量突破策略 (权重 10%)
    价格突破 + 成交量放大确认
    """

    def __init__(self):
        super().__init__("成交量突破", P.get("volume_breakout", 0.10))

    def analyze(self, df):
        if not self.validate_df(df, P["volume_ma"] + 20):
            return {"signal": "HOLD", "score": 0, "details": "数据不足", "raw": {}}

        close = df["close"]
        volume = df["volume"]

        vol_ma = volume.rolling(P["volume_ma"]).mean()
        curr_vol = volume.iloc[-1]
        avg_vol = vol_ma.iloc[-1]

        if pd.isna(avg_vol) or avg_vol == 0:
            return {"signal": "HOLD", "score": 0, "details": "成交量数据不足", "raw": {}}

        vol_ratio = curr_vol / avg_vol

        # 价格变化
        price_change_3d = (close.iloc[-1] / close.iloc[-4] - 1) * 100 if len(df) > 3 else 0

        # 关键价位（近期高低点）
        recent_high = df["high"].iloc[-20:].max()
        recent_low = df["low"].iloc[-20:].min()
        price = close.iloc[-1]

        # 放量突破前高
        if price >= recent_high * 0.99 and vol_ratio >= P["volume_spike_ratio"]:
            score = self.safe_score(0.5 + min(vol_ratio / 5, 0.5))
            signal = "BUY"
            detail = f"放量突破前高! 量比:{vol_ratio:.1f}x, 3日涨幅:{price_change_3d:+.1f}%"
        # 放量跌破前低
        elif price <= recent_low * 1.01 and vol_ratio >= P["volume_spike_ratio"]:
            score = self.safe_score(-0.5 - min(vol_ratio / 5, 0.5))
            signal = "SELL"
            detail = f"放量跌破前低! 量比:{vol_ratio:.1f}x, 3日跌幅:{price_change_3d:+.1f}%"
        # 缩量
        elif vol_ratio < 0.5:
            score = 0
            signal = "HOLD"
            detail = f"缩量(量比:{vol_ratio:.1f}x), 等待方向选择"
        else:
            score = 0.1 if price_change_3d > 0 else -0.1
            signal = "HOLD"
            detail = f"正常量(量比:{vol_ratio:.1f}x), 价格变化:{price_change_3d:+.1f}%"

        return {
            "signal": signal,
            "score": score,
            "details": detail,
            "raw": {"vol_ratio": vol_ratio, "price_change_3d": price_change_3d},
        }


class ATRBreakoutStrategy(BaseStrategy):
    """
    ATR波动率突破策略 (权重 10%)
    价格突破 N 倍 ATR = 趋势启动信号
    """

    def __init__(self):
        super().__init__("ATR突破", P.get("atr_breakout", 0.10))

    def analyze(self, df):
        if not self.validate_df(df, P["atr_period"] + 10):
            return {"signal": "HOLD", "score": 0, "details": "数据不足", "raw": {}}

        atr = ta.volatility.average_true_range(
            df["high"], df["low"], df["close"], P["atr_period"]
        )
        curr_atr = atr.iloc[-1]
        multiplier = P["atr_multiplier"]

        close = df["close"]
        prev_close = close.iloc[-2]
        curr_price = close.iloc[-1]

        upper_break = prev_close + multiplier * curr_atr
        lower_break = prev_close - multiplier * curr_atr

        atr_pct = (curr_atr / curr_price) * 100

        if curr_price > upper_break:
            score = self.safe_score(0.5 + min(atr_pct, 0.5))
            signal = "BUY"
            detail = f"向上ATR突破! 价格${curr_price:,.0f}>上轨${upper_break:,.0f}, ATR={atr_pct:.2f}%"
        elif curr_price < lower_break:
            score = self.safe_score(-0.5 - min(atr_pct, 0.5))
            signal = "SELL"
            detail = f"向下ATR突破! 价格${curr_price:,.0f}<下轨${lower_break:,.0f}, ATR={atr_pct:.2f}%"
        else:
            # 在通道内
            position = (curr_price - lower_break) / (upper_break - lower_break) if upper_break != lower_break else 0.5
            score = self.safe_score((position - 0.5) * 0.4)
            signal = "HOLD"
            detail = f"ATR通道内(位置:{position:.0%}), 上轨${upper_break:,.0f}, 下轨${lower_break:,.0f}"

        return {
            "signal": signal,
            "score": score,
            "details": detail,
            "raw": {"atr": curr_atr, "atr_pct": atr_pct, "upper": upper_break, "lower": lower_break},
        }


# ============================================================
# 综合评分系统
# ============================================================

class CompositeScoringSystem:
    """
    多因子综合评分系统
    汇总所有策略信号，给出综合评分
    """

    def __init__(self):
        self.strategies = [
            # 趋势层 (40%)
            MAAlignmentStrategy(),
            ADXStrengthStrategy(),
            SuperTrendStrategy(),
            # 动量层 (20%)
            MACDMomentumStrategy(),
            OBVTrendStrategy(),
            # 震荡层 (20%)
            RSIDivergenceStrategy(),
            BollingerPositionStrategy(),
            # 量价层 (20%)
            VolumeBreakoutStrategy(),
            ATRBreakoutStrategy(),
        ]

    def analyze(self, df, symbol=""):
        """综合分析"""
        results = {}
        weighted_score = 0
        total_weight = 0

        for strategy in self.strategies:
            try:
                result = strategy.analyze(df)
                results[strategy.name] = result
                weighted_score += result["score"] * strategy.weight
                total_weight += strategy.weight
            except Exception as e:
                results[strategy.name] = {
                    "signal": "HOLD",
                    "score": 0,
                    "details": f"策略异常: {e}",
                    "raw": {},
                }

        # 归一化总分 (-1 ~ 1)
        if total_weight > 0:
            final_score = weighted_score / total_weight
        else:
            final_score = 0

        # 方向判断
        if final_score > 0.3:
            direction = "STRONG_BUY"
        elif final_score > 0.1:
            direction = "BUY"
        elif final_score < -0.3:
            direction = "STRONG_SELL"
        elif final_score < -0.1:
            direction = "SELL"
        else:
            direction = "HOLD"

        # 置信度 (0~1)
        buy_count = sum(1 for r in results.values() if r["signal"] == "BUY")
        sell_count = sum(1 for r in results.values() if r["signal"] == "SELL")
        total_signals = buy_count + sell_count
        confidence = max(buy_count, sell_count) / total_signals if total_signals > 0 else 0

        return {
            "symbol": symbol,
            "total_score": round(final_score, 4),
            "direction": direction,
            "confidence": round(confidence, 2),
            "price": df["close"].iloc[-1] if not df.empty else 0,
            "factor_scores": {name: round(r["score"], 3) for name, r in results.items()},
            "details": {name: r["details"] for name, r in results.items()},
            "raw_data": {name: r["raw"] for name, r in results.items()},
        }

    def analyze_multi_timeframe(self, dfs: dict, symbol=""):
        """
        多时间框架分析
        dfs: {"weekly": df_w, "daily": df_d, "4h": df_4h}
        周线定方向，日线找入场，4H找精确点
        """
        results = {}
        for tf_name, df in dfs.items():
            if df is not None and not df.empty:
                results[tf_name] = self.analyze(df, symbol)

        # 综合多时间框架
        if not results:
            return None

        # 权重: 周线30%, 日线50%, 4H 20%
        tf_weights = {"weekly": 0.3, "daily": 0.5, "4h": 0.2}

        combined_score = 0
        combined_weight = 0
        for tf, weight in tf_weights.items():
            if tf in results:
                combined_score += results[tf]["total_score"] * weight
                combined_weight += weight

        if combined_weight > 0:
            combined_score /= combined_weight

        # 方向一致性检查
        directions = [r["direction"] for r in results.values()]
        bullish_count = sum(1 for d in directions if "BUY" in d)
        bearish_count = sum(1 for d in directions if "SELL" in d)

        if bullish_count >= 2:
            overall = "STRONG_BUY" if combined_score > 0.3 else "BUY"
        elif bearish_count >= 2:
            overall = "STRONG_SELL" if combined_score < -0.3 else "SELL"
        else:
            overall = "HOLD"

        return {
            "symbol": symbol,
            "total_score": round(combined_score, 4),
            "direction": overall,
            "timeframe_results": results,
            "alignment": f"多周期一致度: 多{bullish_count}/空{bearish_count}/中性{len(directions)-bullish_count-bearish_count}",
        }
