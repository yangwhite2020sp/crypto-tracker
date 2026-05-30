"""
CryptoTracker Pro - 数据库模块
"""
import os
import sqlite3
import pandas as pd
from datetime import datetime
from config import DATABASE_PATH


def get_db_path():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    return DATABASE_PATH


def get_conn():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_conn()
    c = conn.cursor()

    # K线数据表
    c.execute("""
        CREATE TABLE IF NOT EXISTS klines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            open_time INTEGER NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            close_time INTEGER,
            quote_volume REAL,
            trades_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, interval, open_time)
        )
    """)

    # 策略信号表
    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            strategy TEXT NOT NULL,
            signal TEXT NOT NULL,
            score REAL,
            price REAL,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 综合评分表
    c.execute("""
        CREATE TABLE IF NOT EXISTS composite_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            total_score REAL,
            direction TEXT,
            confidence REAL,
            factor_scores TEXT,
            price REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 告警记录表
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT,
            score REAL,
            price REAL,
            sent INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 创建索引
    c.execute("CREATE INDEX IF NOT EXISTS idx_klines_symbol_interval ON klines(symbol, interval, open_time)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol, created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_composite_symbol ON composite_scores(symbol, interval, created_at)")

    conn.commit()
    conn.close()
    print("[DB] 数据库初始化完成")


def save_klines(symbol, interval, klines_data):
    """保存K线数据"""
    conn = get_conn()
    c = conn.cursor()
    inserted = 0
    for k in klines_data:
        try:
            c.execute("""
                INSERT OR REPLACE INTO klines
                (symbol, interval, open_time, open, high, low, close, volume,
                 close_time, quote_volume, trades_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol, interval,
                int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]),
                float(k[5]), int(k[6]), float(k[7]), int(k[8])
            ))
            inserted += 1
        except Exception as e:
            pass
    conn.commit()
    conn.close()
    return inserted


def get_klines(symbol, interval, limit=200):
    """获取K线数据，返回DataFrame"""
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT open_time, open, high, low, close, volume, close_time
        FROM klines
        WHERE symbol = ? AND interval = ?
        ORDER BY open_time DESC
        LIMIT ?
    """, conn, params=(symbol, interval, limit))
    conn.close()
    if not df.empty:
        df = df.sort_values("open_time").reset_index(drop=True)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
    return df


def save_signal(symbol, interval, strategy, signal, score, price, details=""):
    """保存策略信号"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO signals (symbol, interval, strategy, signal, score, price, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (symbol, interval, strategy, signal, score, price, details))
    conn.commit()
    conn.close()


def get_latest_signals(symbol, limit=50):
    """获取最新信号"""
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT * FROM signals
        WHERE symbol = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, conn, params=(symbol, limit))
    conn.close()
    return df


def save_composite_score(symbol, interval, total_score, direction, confidence, factor_scores, price):
    """保存综合评分"""
    import json
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO composite_scores (symbol, interval, total_score, direction, confidence, factor_scores, price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (symbol, interval, total_score, direction, confidence, json.dumps(factor_scores), price))
    conn.commit()
    conn.close()


def get_latest_composite_scores():
    """获取所有币种的最新综合评分"""
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT cs.* FROM composite_scores cs
        INNER JOIN (
            SELECT symbol, interval, MAX(created_at) as max_time
            FROM composite_scores
            GROUP BY symbol, interval
        ) latest ON cs.symbol = latest.symbol AND cs.interval = latest.interval AND cs.created_at = latest.max_time
        ORDER BY cs.symbol, cs.interval
    """, conn)
    conn.close()
    return df


def save_alert(symbol, alert_type, message, score=None, price=None):
    """保存告警"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO alerts (symbol, alert_type, message, score, price)
        VALUES (?, ?, ?, ?, ?)
    """, (symbol, alert_type, message, score, price))
    conn.commit()
    conn.close()


def get_unsent_alerts():
    """获取未发送的告警"""
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT * FROM alerts WHERE sent = 0 ORDER BY created_at ASC
    """, conn)
    conn.close()
    return df


def mark_alerts_sent(alert_ids):
    """标记告警已发送"""
    conn = get_conn()
    c = conn.cursor()
    for aid in alert_ids:
        c.execute("UPDATE alerts SET sent = 1 WHERE id = ?", (aid,))
    conn.commit()
    conn.close()


def get_data_status():
    """获取数据状态"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT symbol, interval, COUNT(*) as count, MAX(open_time) as latest
        FROM klines GROUP BY symbol, interval
    """)
    rows = c.fetchall()
    conn.close()
    status = {}
    for row in rows:
        key = f"{row[0]}_{row[1]}"
        status[key] = {
            "symbol": row[0],
            "interval": row[1],
            "count": row[2],
            "latest": pd.to_datetime(row[3], unit="ms") if row[3] else None,
        }
    return status
