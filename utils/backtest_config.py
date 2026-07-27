"""
回测配置的轻量封装
供策略、Broker、分析模块等统一读取回测相关配置（冗余开关、评价指标参数、回测区间），
避免多处重复解析 config.ini。
"""
import os
import configparser
from typing import Optional, Tuple

# 缓存：策略初始化时会 refresh，Broker / 策略 / 分析模块共用同一份
_cached_cfg: Optional[configparser.ConfigParser] = None


def refresh_backtest_config() -> None:
    """
    刷新回测配置缓存（在每次策略实例化时调用，保证长生命周期进程使用最新配置）。
    """
    global _cached_cfg
    _cached_cfg = None


def _get_cfg() -> configparser.ConfigParser:
    """读取并缓存 config.ini（解析一次，供本模块各读取函数共用）。"""
    global _cached_cfg
    if _cached_cfg is None:
        cfg = configparser.ConfigParser()
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg.read(os.path.join(project_root, "config.ini"), encoding="utf-8")
        _cached_cfg = cfg
    return _cached_cfg


def is_verbose_mode() -> bool:
    """
    判断当前是否为冗余(verbose)模式。
    配置 [BACKTEST] verbose = True 时，策略与 Broker 会输出更详细的日志（如每笔买卖明细）。

    Returns:
        bool: True=冗余模式，False=简约模式。
    """
    try:
        return _get_cfg().getboolean("BACKTEST", "verbose", fallback=False)
    except (TypeError, ValueError):
        return False


def get_metrics_params() -> Tuple[float, int]:
    """
    读取评价指标参数，供夏普/年化/Sortino 等计算使用。

    Returns:
        tuple: (risk_free_rate 年化无风险利率-小数, trading_days_per_year 年化交易日数)
    """
    cfg = _get_cfg()
    risk_free_rate = cfg.getfloat("BACKTEST", "risk_free_rate", fallback=0.0)
    trading_days = cfg.getint("BACKTEST", "trading_days_per_year", fallback=252)
    return risk_free_rate, trading_days


def get_backtest_end_time(fallback: str = "") -> str:
    """读取回测结束日 [BACKTEST] backtest_end_time；缺省时返回 fallback。"""
    return _get_cfg().get("BACKTEST", "backtest_end_time", fallback=fallback)


def get_risk_metric_basis() -> str:
    """
    风险类指标（波动率/夏普/索提诺）的日收益样本口径。

    配置 [BACKTEST] risk_metric_basis：
    - 'active'（默认）：仅统计有持仓或净值有波动的交易日，剔除纯空仓静止日的 0% 收益，
      避免其稀释标准差、虚高夏普/索提诺；
    - 'all'：使用全部相邻日收益（含空仓静止日，旧口径）。

    Returns:
        str: 'active' 或 'all'。
    """
    val = _get_cfg().get("BACKTEST", "risk_metric_basis", fallback="active").strip().lower()
    return val if val in ("active", "all") else "active"
