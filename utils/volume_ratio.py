"""
日线量比计算（与常见行情软件日频近似一致，供选股等指标复用）。
"""
from __future__ import annotations

import math

import pandas as pd


def compute_volume_ratio_daily(df: pd.DataFrame, avg_days: int = 5) -> float:
    """
    量比（日线口径）：当日总成交量 / 过去 avg_days 个交易日日均总成交量（不含当日）。

    Args:
        df: 按日期升序排列的日线，最后一行为「当日」；需含 volume 列。
        avg_days: 均量回溯交易日数，默认 5（对应常见「量比」五日均量）。

    Returns:
        float: 量比；数据不足或均量无效时返回 nan。
    """
    if df is None or getattr(df, "empty", True) or len(df) < avg_days + 1:
        return float("nan")
    today_vol = float(df.iloc[-1]["volume"])
    past = df.iloc[-(avg_days + 1) : -1]["volume"].astype(float)
    mean_vol = float(past.mean())
    if mean_vol <= 0 or math.isnan(mean_vol):
        return float("nan")
    if today_vol <= 0:
        return float("nan")
    return today_vol / mean_vol
