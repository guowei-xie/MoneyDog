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
# 内存覆盖配置：一旦安装则所有读取优先使用它、不落盘，且不被无参 refresh 清除。
# 用于 Web「仅本次运行」——用请求参数构造内存配置驱动本次回测，而不改写磁盘 config.ini。
# 注意：本模块不提供并发保护，其单实例安全性依赖 web/server.py 的单回测槽位（_RUN_LOCK + 409 守卫）。
_override_cfg: Optional[configparser.ConfigParser] = None


def refresh_backtest_config() -> None:
    """
    刷新回测配置缓存（在每次策略实例化时调用，保证长生命周期进程使用最新配置）。

    仅清空磁盘解析缓存，下次从 config.ini 重新读取；不影响已安装的内存覆盖配置，
    因此 Web「仅本次运行」期间策略实例化时的 refresh 不会丢弃本次回测的内存配置。
    """
    global _cached_cfg
    _cached_cfg = None


def set_backtest_config_override(cfg: configparser.ConfigParser) -> None:
    """安装内存覆盖配置：后续读取一律使用它、不落盘（Web「仅本次运行」入口）。"""
    global _override_cfg
    _override_cfg = cfg


def clear_backtest_config_override() -> None:
    """清除内存覆盖配置，恢复从 config.ini 读取（Web 回测结束后调用）。"""
    global _override_cfg
    _override_cfg = None


def get_config_path() -> str:
    """返回 config.ini 的绝对路径（基于本文件定位项目根，消除对当前工作目录的依赖）。"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "config.ini")


def _get_cfg() -> configparser.ConfigParser:
    """读取配置：内存覆盖配置优先；否则读取并缓存 config.ini（解析一次，共用）。"""
    global _cached_cfg
    if _override_cfg is not None:
        return _override_cfg
    if _cached_cfg is None:
        cfg = configparser.ConfigParser()
        cfg.read(get_config_path(), encoding="utf-8")
        _cached_cfg = cfg
    return _cached_cfg


def get_cfg() -> configparser.ConfigParser:
    """
    返回共享的、已缓存的 config.ini 解析结果。

    供 Broker / BaseStrategy 等复用，替代各处自建 configparser + 相对路径 read，
    统一走 __file__ 定位的绝对路径，消除 CWD 依赖与重复解析。
    """
    return _get_cfg()


def get_data_path() -> str:
    """[DATA] data_path：DuckDB 数据库路径。"""
    return _get_cfg().get("DATA", "data_path", fallback="")


def get_log_level(fallback: str = "INFO") -> str:
    """[LOGGING] level：日志级别（大写字符串）。"""
    return _get_cfg().get("LOGGING", "level", fallback=fallback).upper()


def get_strategy_target() -> Tuple[str, str]:
    """[STRATEGY] (strategy_module, strategy_class)：待加载策略的模块名与类名。"""
    cfg = _get_cfg()
    return cfg.get("STRATEGY", "strategy_module"), cfg.get("STRATEGY", "strategy_class")


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
