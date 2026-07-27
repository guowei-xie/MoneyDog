"""
MoneyDog Web 模块数据模型定义。

该模块集中维护 Web 层使用的 Pydantic 模型，避免在 `server.py`
中堆积过多类定义，提升可读性与可维护性。
"""

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator

_DATE_RE = re.compile(r"^\d{8}$")


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

    @field_validator("backtest_start_time", "backtest_end_time")
    @classmethod
    def _check_date_format(cls, v: str) -> str:
        """校验日期为 8 位数字（YYYYMMDD）。"""
        if not _DATE_RE.match(v.strip()):
            raise ValueError("日期格式应为 YYYYMMDD（8 位数字）")
        return v.strip()

    @field_validator("initial_amount")
    @classmethod
    def _check_initial_amount(cls, v: float) -> float:
        """初始资金必须为正。"""
        if v <= 0:
            raise ValueError("初始资金必须大于 0")
        return v

    @field_validator("commission_rate", "min_commission", "tax_rate", "max_vol_rate", "max_vol_amount")
    @classmethod
    def _check_non_negative(cls, v: float) -> float:
        """费用与仓位上限参数不得为负。"""
        if v < 0:
            raise ValueError("该参数不得为负")
        return v

    @field_validator("limit_vol_type")
    @classmethod
    def _check_limit_vol_type(cls, v: str) -> str:
        """仓位控制方式仅允许 amount / ratio。"""
        if v not in ("amount", "ratio"):
            raise ValueError("limit_vol_type 仅支持 'amount' 或 'ratio'")
        return v

    @field_validator("batch_stock_selection_threads")
    @classmethod
    def _check_threads(cls, v: int) -> int:
        """线程数不得为负（0=自动）。"""
        if v < 0:
            raise ValueError("线程数不得为负")
        return v

    @model_validator(mode="after")
    def _check_period(self) -> "BacktestConfig":
        """开始日期不得晚于结束日期。"""
        if self.backtest_start_time > self.backtest_end_time:
            raise ValueError("开始日期不得晚于结束日期")
        return self


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

