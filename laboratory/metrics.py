"""
账户收益类评价指标的纯函数实现（仅依赖 pandas/numpy，无 IO / 无 DuckDB），便于离线单测复用。

从 laboratory.analyze 中抽出「波动率 / 夏普 / 索提诺」的日收益口径与计算，
核心动机：原实现用 total_assets.pct_change() 把**纯空仓静止日的 0% 收益**计入样本，
本策略族频繁空仓，大量 0% 会压低日收益标准差，从而系统性高估夏普/索提诺/年化波动。
"""
from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd

_EPS = 1e-12


def build_risk_return_series(
    total_assets, stock_count, basis: str = "active"
) -> Tuple[pd.Series, int]:
    """
    由每日总资产序列构造用于波动/夏普/索提诺的日收益样本。

    Args:
        total_assets: 每日总资产序列（按日期升序）。
        stock_count: 与 total_assets 对齐的每日持仓股票数（日终口径）。
        basis: 'all'  使用全部相邻日收益（含空仓静止日的 0% 收益，旧口径）；
               'active' 仅保留「当日有持仓 或 当日净值有波动（含日内回转）」的交易日，
                        剔除纯空仓静止日的 0% 收益（默认，避免稀释波动）。

    Returns:
        (returns, sample_days): 用于风险指标的日收益 Series 及其样本天数。
    """
    ta = pd.Series(total_assets, dtype=float).reset_index(drop=True)
    daily = ta.pct_change()
    if basis == "all":
        r = daily.dropna()
        return r, int(r.shape[0])
    sc = pd.Series(stock_count).reset_index(drop=True)
    # 活跃日：当日有持仓，或当日净值有波动（含日内回转）；纯空仓静止日的 0% 收益被剔除。
    # 首日 pct_change 为 NaN，会被下方 dropna 一并剔除，无需单独处理首日。
    exposed = (sc > 0) | (daily.abs() > _EPS)
    r = daily[exposed].dropna()
    return r, int(r.shape[0])


def compute_return_risk_metrics(returns, rf_daily: float, ann_factor: float) -> dict:
    """
    由日收益样本计算风险类指标：日均收益、样本标准差(ddof=1)、年化波动率、年化夏普、年化索提诺。

    样本不足（n<2）或标准差非正时，相应指标返回 nan。

    Args:
        returns: 日收益样本（Series 或可转序列）。
        rf_daily: 日度无风险利率。
        ann_factor: 年化因子（通常为 sqrt(交易日/年)）。

    Returns:
        dict: {mean, std, annual_volatility, sharpe, sortino}
    """
    r = pd.Series(returns, dtype=float)
    n = r.shape[0]
    mean_ret = r.mean() if n > 0 else np.nan
    std = r.std(ddof=1) if n > 1 else np.nan
    annual_volatility = std * ann_factor if pd.notnull(std) and std > 0 else np.nan
    sharpe = (mean_ret - rf_daily) / std * ann_factor if pd.notnull(std) and std > 0 else np.nan
    downside_std = r[r < rf_daily].std(ddof=1)
    sortino = (
        (mean_ret - rf_daily) / downside_std * ann_factor
        if pd.notnull(downside_std) and downside_std > 0
        else np.nan
    )
    return {
        "mean": mean_ret,
        "std": std,
        "annual_volatility": annual_volatility,
        "sharpe": sharpe,
        "sortino": sortino,
    }
