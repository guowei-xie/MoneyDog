"""
MoneyDog Web 模块数据模型定义。

该模块集中维护 Web 层使用的 Pydantic 模型，避免在 `server.py`
中堆积过多类定义，提升可读性与可维护性。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class StrategyInfo(BaseModel):
    """
    策略基本信息模型，用于前端展示策略模块与类名。
    """

    module: str
    classes: List[str]


class StrategyConfig(BaseModel):
    """
    策略配置模型，对应 config.ini 中 [STRATEGY] 段。
    """

    strategy_module: str
    strategy_class: str


class BacktestConfig(BaseModel):
    """
    回测配置模型，对应 config.ini 中 [BACKTEST] 段的主要字段。
    """

    backtest_start_time: str
    backtest_end_time: str
    initial_amount: float
    commission_rate: float
    min_commission: float
    tax_rate: float
    limit_vol_type: str
    max_vol_rate: float
    max_vol_amount: float
    # 选股是否使用多线程（False=单线程，便于开发调试）
    batch_stock_selection_use_threads: bool
    # 多线程选股时的线程数（仅 use_threads=True 时生效，0=自动）
    batch_stock_selection_threads: int


class RunBacktestRequest(BaseModel):
    """
    运行回测请求模型，封装策略选择与回测参数。
    """

    strategy: StrategyConfig
    backtest: BacktestConfig


class RunRecord(BaseModel):
    """
    回测运行记录模型，记录单次回测的关键信息。
    """

    id: str
    created_at: str
    strategy: StrategyConfig
    backtest: BacktestConfig
    files: Dict[str, str]
    metrics: Optional[Dict[str, Any]] = None
    summary: Optional[Dict[str, Any]] = None

