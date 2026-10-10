"""模块5：策略回测引擎（向量化，纯 pandas/numpy，零额外依赖）。

支持策略：双均线 / MACD / RSI 超买超卖 / 布林带。
回测口径：
  - 初始资金、全仓买卖（持仓 1 / 空仓 0）
  - 信号产生于收盘，当日收盘调仓，按收盘→收盘日收益近似
  - 单边佣金 fee（默认万 2.5），换仓当日计提
  - 输入 df 需含列 date/open/high/low/close，按日期升序排列
"""
import numpy as np
import pandas as pd


# ---- 策略信号（返回 0/1 持仓序列，与 df 等长）----

def ma_signal(df: pd.DataFrame, short: int = 5, long: int = 20) -> pd.Series:
    """双均线：短均线上穿长均线后持仓(1)，下穿后空仓(0)。"""
    short_ma = df["close"].rolling(short).mean()
    long_ma = df["close"].rolling(long).mean()
    return (short_ma > long_ma).astype(float)


def macd_signal(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    """MACD：DIF > DEA 持仓，否则空仓。"""
    dif = df["close"].ewm(span=fast, adjust=False).mean() - df["close"].ewm(span=slow, adjust=False).mean()
    dea = dif.ewm(span=signal, adjust=False).mean()
    return (dif > dea).astype(float)


def rsi_signal(df: pd.DataFrame, period: int = 14, low: float = 30, high: float = 70) -> pd.Series:
    """RSI：低于超卖阈值买入，高于超买阈值卖出，其余维持前值。"""
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    pos = np.where(rsi < low, 1.0, np.where(rsi > high, 0.0, np.nan))
    return pd.Series(pos, index=df.index).ffill().fillna(0.0)


def boll_signal(df: pd.DataFrame, period: int = 20, k: float = 2.0) -> pd.Series:
    """布林带：收盘跌破下轨买入，突破上轨卖出，其余维持前值。"""
    mid = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    lower = mid - k * std
    upper = mid + k * std
    close = df["close"]
    pos = np.where(close < lower, 1.0, np.where(close > upper, 0.0, np.nan))
    return pd.Series(pos, index=df.index).ffill().fillna(0.0)


# ---- 策略注册表 ----

STRATEGIES = {
    "双均线（MA）": {"fn": ma_signal, "params": {"short": 5, "long": 20}},
    "MACD": {"fn": macd_signal, "params": {"fast": 12, "slow": 26, "signal": 9}},
    "RSI 超买超卖": {"fn": rsi_signal, "params": {"period": 14, "low": 30, "high": 70}},
    "布林带（BOLL）": {"fn": boll_signal, "params": {"period": 20, "k": 2.0}},
}


# ---- 回测引擎 ----

def run_backtest(df: pd.DataFrame, position: pd.Series, initial: float = 100000.0,
                 fee: float = 0.00025):
    """执行回测，返回 (metrics, back_df, trades)。

    back_df 在原 df 基础上追加 equity（策略净值）、bench（买入持有净值）两列。
    trades 含 buy_idx / sell_idx（买卖点在 back_df 中的行索引）。
    """
    df = df.copy().reset_index(drop=True)
    df["ret"] = df["close"].pct_change().fillna(0.0)

    pos = position.reindex(df.index).fillna(0.0).astype(float)
    prev_pos = pos.shift(1).fillna(0.0)
    turnover = (pos - prev_pos).abs()  # 换手仓位，用于计提佣金

    strat_ret = prev_pos * df["ret"] - turnover * fee
    bench_ret = df["ret"]

    df["equity"] = initial * (1 + strat_ret).cumprod()
    df["bench"] = initial * (1 + bench_ret).cumprod()

    metrics = _metrics(df, strat_ret, pos, initial)
    trades = _trade_stats(df, pos)
    return metrics, df, trades


def _metrics(df: pd.DataFrame, strat_ret: pd.Series, pos: pd.Series, initial: float) -> dict:
    n = len(df)
    years = n / 252.0
    equity = df["equity"]
    total_ret = equity.iloc[-1] / initial - 1
    annual = ((1 + total_ret) ** (1 / years) - 1) if years > 0 and total_ret > -1 else 0.0

    dd = equity / equity.cummax() - 1
    max_dd = float(dd.min())

    std = float(strat_ret.std())
    sharpe = float(strat_ret.mean() / std * np.sqrt(252)) if std and std > 0 else 0.0

    bench_total = df["bench"].iloc[-1] / initial - 1
    trades = _trade_stats(df, pos)

    return {
        "总收益率": float(total_ret),
        "年化收益率": float(annual),
        "最大回撤": max_dd,
        "夏普比率": sharpe,
        "交易次数": trades["trades"],
        "胜率": trades["win_rate"],
        "买入持有收益": float(bench_total),
        "期末资金": float(equity.iloc[-1]),
        "回测天数": n,
    }


def _trade_stats(df: pd.DataFrame, pos: pd.Series) -> dict:
    """配对买卖点，统计交易次数与胜率（买入成交价→卖出成交价）。"""
    buy_idx, sell_idx = [], []
    in_pos = False
    buy_price = None
    wins = 0
    total = 0

    for i in range(len(df)):
        p = pos.iloc[i]
        if p > 0 and not in_pos:
            in_pos = True
            buy_price = df["close"].iloc[i]
            buy_idx.append(i)
        elif p <= 0 and in_pos:
            in_pos = False
            total += 1
            if df["close"].iloc[i] > buy_price:
                wins += 1
            sell_idx.append(i)

    if in_pos:  # 期末仍持仓，按最后收盘价平仓
        total += 1
        if df["close"].iloc[-1] > buy_price:
            wins += 1
        sell_idx.append(len(df) - 1)

    win_rate = wins / total if total > 0 else 0.0
    return {"trades": total, "win_rate": win_rate, "buy_idx": buy_idx, "sell_idx": sell_idx}
