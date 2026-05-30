"""
CryptoTracker Pro - 策略基类
"""
import pandas as pd
import numpy as np


class BaseStrategy:
    """策略基类"""

    def __init__(self, name, weight=1.0):
        self.name = name
        self.weight = weight

    def analyze(self, df: pd.DataFrame) -> dict:
        """
        分析K线数据
        返回: {
            "signal": "BUY" | "SELL" | "HOLD",
            "score": float (-1.0 ~ 1.0),
            "details": str,
            "raw": dict  # 原始指标数据
        }
        """
        raise NotImplementedError

    @staticmethod
    def validate_df(df: pd.DataFrame, min_rows=100):
        """验证数据是否足够"""
        if df is None or df.empty or len(df) < min_rows:
            return False
        required_cols = ["open", "high", "low", "close", "volume"]
        return all(col in df.columns for col in required_cols)

    @staticmethod
    def safe_score(value, min_val=-1.0, max_val=1.0):
        """安全地限制分数范围"""
        return max(min_val, min(max_val, float(value)))
