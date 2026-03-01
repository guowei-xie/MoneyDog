"""
回测配置的轻量封装
供策略、Broker 等统一读取回测相关开关（如冗余模式），避免多处重复解析 config.ini。
"""
import os
import configparser
from typing import Optional

# 缓存：策略初始化时会 refresh，Broker 与策略共用同一份
_cached_verbose: Optional[bool] = None


def refresh_backtest_config() -> None:
    """
    刷新回测配置缓存（在每次策略实例化时调用，保证长生命周期进程使用最新配置）。
    """
    global _cached_verbose
    _cached_verbose = None


def is_verbose_mode() -> bool:
    """
    判断当前是否为冗余(verbose)模式。
    配置 [BACKTEST] verbose = True 时，策略与 Broker 会输出更详细的日志（如每笔买卖明细）。

    Returns:
        bool: True=冗余模式，False=简约模式。
    """
    global _cached_verbose
    if _cached_verbose is None:
        cfg = configparser.ConfigParser()
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, "config.ini")
        cfg.read(config_path, encoding="utf-8")
        try:
            _cached_verbose = cfg.getboolean("BACKTEST", "verbose", fallback=False)
        except (TypeError, ValueError):
            _cached_verbose = False
    return bool(_cached_verbose)
