"""
MoneyDog Web 服务入口
基于 FastAPI 提供 Web API 与简易前端界面。
"""

import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
import shutil

import configparser
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from main import load_strategy
from utils.backtest_config import (
    clear_backtest_config_override,
    get_config_path,
    set_backtest_config_override,
)
from utils.data import (
    get_daily_bars,
    get_data_coverage,
    get_overall_coverage,
    get_stock_list_in_sector,
    has_index_1day_data,
)
from utils.logger import error, info
from laboratory.analyze import (
    analyze_account_changes,
    compute_account_series,
    load_account_changes_df,
    summarize_trades,
    format_trade_summary,
    fmt_metric,
)
from app import ConfigApp
from web.schemas import (
    BacktestConfig,
    RunBacktestRequest,
    RunRecord,
    StrategyConfig,
    StrategyInfo,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
RUN_INDEX_PATH = os.path.join(RESULTS_DIR, "run_index.json")

# 前端构建产物目录（web/frontend/dist），由 Vue SPA `npm run build` 生成
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")
FRONTEND_INDEX = os.path.join(FRONTEND_DIST, "index.html")
FRONTEND_ASSETS = os.path.join(FRONTEND_DIST, "assets")

# 当前正在后台运行的回测任务信息（用于中止回测与运行态恢复）
# run_id 一旦置位即视为“运行中”；strategy 由后台线程注入，供中止使用。
CURRENT_BACKTEST: Dict[str, Any] = {
    "run_id": None,
    "strategy": None,
    "strategy_label": None,
    "started_at": None,
    "backtest_period": None,
}

# 保证「检查是否有回测在跑 + 占位」原子化，避免并发提交竞态
_RUN_LOCK = threading.Lock()

# 最近一次结束的回测信息，供前端在刷新/轮询时从 running -> finished 自动跳转结果页
LAST_FINISHED: Dict[str, Any] = {
    "run_id": None,
    "status": None,  # success/failed/stopped
}

# 当前回测进度信息（供前端查询进度展示）
BACKTEST_PROGRESS: Dict[str, Any] = {
    "run_id": None,
    "stage": "idle",  # idle/selection/backtest
    "current": 0,
    "total": 0,
    "percent": 0.0,
}


def _reset_current_backtest() -> None:
    """清空当前运行信息（回测结束后调用）。"""
    CURRENT_BACKTEST.update(
        run_id=None,
        strategy=None,
        strategy_label=None,
        started_at=None,
        backtest_period=None,
    )


def _ensure_results_dir() -> None:
    """
    确保 results 目录存在。
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)


def _snapshot_results_files() -> Dict[str, float]:
    """
    获取当前 results 目录下文件的快照（文件名 -> 修改时间）。

    Returns:
        dict: {文件名: 修改时间戳}
    """
    _ensure_results_dir()
    snapshot: Dict[str, float] = {}
    for name in os.listdir(RESULTS_DIR):
        path = os.path.join(RESULTS_DIR, name)
        if os.path.isfile(path):
            snapshot[name] = os.path.getmtime(path)
    return snapshot


def _diff_results_files(
    before: Dict[str, float],
    after: Dict[str, float],
) -> List[str]:
    """
    对比回测前后 results 目录，找出新增或更新的文件名列表。

    Args:
        before: 回测前的文件快照
        after: 回测后的文件快照

    Returns:
        list[str]: 新增或被更新的文件名列表
    """
    changed: List[str] = []
    for name, mtime in after.items():
        if name not in before or mtime > before.get(name, 0):
            changed.append(name)
    return sorted(changed)


# run_index.json 解析缓存（按文件 mtime 失效）：单页结果视图会连续多次读取索引，
# 避免每次都重新 json.load + Pydantic 校验整份记录。
_RUN_INDEX_CACHE: Optional[List[RunRecord]] = None
_RUN_INDEX_MTIME: float = 0.0


def _load_run_index() -> List[RunRecord]:
    """
    加载 run_index.json 中的所有回测记录（按 mtime 命中缓存）。

    返回缓存列表的浅拷贝：允许调用方增删列表结构而不污染缓存，
    对记录对象字段的就地修改仍会在 _save_run_index 时落盘。

    Returns:
        list[RunRecord]: 回测记录列表
    """
    global _RUN_INDEX_CACHE, _RUN_INDEX_MTIME
    _ensure_results_dir()
    if not os.path.exists(RUN_INDEX_PATH):
        return []
    mtime = os.path.getmtime(RUN_INDEX_PATH)
    if _RUN_INDEX_CACHE is not None and mtime == _RUN_INDEX_MTIME:
        return list(_RUN_INDEX_CACHE)
    try:
        with open(RUN_INDEX_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        records = [RunRecord(**item) for item in raw]
    except Exception as exc:  # noqa: BLE001
        error(f"加载回测索引失败: {exc}")
        return []
    _RUN_INDEX_CACHE = records
    _RUN_INDEX_MTIME = mtime
    return list(records)


def _save_run_index(records: List[RunRecord]) -> None:
    """
    将回测记录列表写入 run_index.json，并同步刷新解析缓存。

    Args:
        records: 回测记录列表
    """
    global _RUN_INDEX_CACHE, _RUN_INDEX_MTIME
    _ensure_results_dir()
    try:
        payload = [record.model_dump() for record in records]
        with open(RUN_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        _RUN_INDEX_CACHE = list(records)
        _RUN_INDEX_MTIME = os.path.getmtime(RUN_INDEX_PATH)
    except Exception as exc:  # noqa: BLE001
        error(f"保存回测索引失败: {exc}")


def _get_record_or_404(run_id: str) -> RunRecord:
    """按 run_id 查找回测记录，未找到抛 404（消除各端点重复的查找+404 样板）。"""
    target = next((r for r in _load_run_index() if r.id == run_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="未找到对应回测记录")
    return target


def _strategy_label(strategy: StrategyConfig) -> str:
    """策略展示标签：module.class。"""
    return f"{strategy.strategy_module}.{strategy.strategy_class}"


def _build_default_backtest_config(cfg: configparser.ConfigParser) -> BacktestConfig:
    """
    从 configparser 对象中构造 BacktestConfig。

    Args:
        cfg: 已加载的配置对象

    Returns:
        BacktestConfig: 回测配置模型
    """
    section = "BACKTEST"
    return BacktestConfig(
        backtest_start_time=cfg.get(section, "backtest_start_time", fallback="20250101"),
        backtest_end_time=cfg.get(section, "backtest_end_time", fallback="20250131"),
        initial_amount=cfg.getfloat(section, "initial_amount", fallback=1_000_000),
        commission_rate=cfg.getfloat(section, "commission_rate", fallback=0.0001),
        min_commission=cfg.getfloat(section, "min_commission", fallback=5.0),
        tax_rate=cfg.getfloat(section, "tax_rate", fallback=0.0005),
        limit_vol_type=cfg.get(section, "limit_vol_type", fallback="amount"),
        max_vol_rate=cfg.getfloat(section, "max_vol_rate", fallback=0.05),
        max_vol_amount=cfg.getfloat(section, "max_vol_amount", fallback=100_000),
        batch_stock_selection_use_threads=cfg.getboolean(
            section,
            "batch_stock_selection_use_threads",
            fallback=True,
        ),
        batch_stock_selection_threads=cfg.getint(
            section,
            "batch_stock_selection_threads",
            fallback=0,
        ),
    )


def _json_safe_cell(value: Any) -> Any:
    """单个单元格转 JSON 安全值：时间转 ISO、numpy 转原生、NaN 转 None。"""
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    return None if isinstance(value, float) and pd.isna(value) else value


def _extract_metrics_from_df(df: pd.DataFrame) -> Dict[str, Any]:
    """
    将 analyze_account_changes 返回的单行 DataFrame 转换为 JSON 安全 dict。

    Args:
        df: 账户分析结果 DataFrame

    Returns:
        dict: 账户指标字典
    """
    if df is None or df.empty:
        return {}
    return {key: _json_safe_cell(value) for key, value in df.iloc[0].to_dict().items()}


# analyze_transactions Excel 中文列 -> 前端稳定英文键
_TRADE_COL_MAP = {
    "股票代码": "code",
    "建仓时间": "open_time",
    "建仓价格": "open_price",
    "清仓时间": "close_time",
    "清仓价格": "close_price",
    "涨跌幅": "net_pct",
    "毛涨跌幅": "gross_pct",
    "是否平仓": "closed",
    "持仓天数": "hold_days",
    "总手续费": "commission",
    "总印花税": "tax",
    "总成本": "cost",
    "备注": "remark",
}


def _json_safe_records(df: pd.DataFrame, rename: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    将 DataFrame 转为 JSON 安全的记录列表：numpy 类型转原生、NaN 转 None、时间转 ISO。

    Args:
        df: 源 DataFrame
        rename: 可选列名映射（中文列 -> 英文键）

    Returns:
        list[dict]: 每行一条记录
    """
    if df is None or df.empty:
        return []
    if rename:
        df = df.rename(columns=rename)
    return [{key: _json_safe_cell(value) for key, value in row.items()} for _, row in df.iterrows()]


def _fmt_trade_date(value: Any) -> str:
    """将 trade_date（如 20250701 / '20250701'）格式化为 YYYY-MM-DD 显示串。"""
    s = str(value).replace("-", "")[:8]
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else str(value)


def _bars_to_json(df: pd.DataFrame, period: str) -> List[Dict[str, Any]]:
    """
    将 get_daily_bars 返回的单只 DataFrame 转为前端 K 线数组。

    Args:
        df: 行情 DataFrame，index 为 'YYYYMMDD'（日线）或 'YYYYMMDDHHMMSS'（分钟线）
        period: '1d' 或 '1m'，决定 date 显示粒度

    Returns:
        list[dict]: [{date, open, high, low, close, volume}, ...]
    """
    if df is None or df.empty:
        return []
    bars: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        s = str(idx)
        date = (
            f"{s[:4]}-{s[4:6]}-{s[6:8]}"
            if period == "1d"
            else f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
        )
        bars.append(
            {
                "date": date,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )
    return bars


def _build_account_summary(metrics: Dict[str, Any]) -> List[str]:
    """
    构造账户分析结果摘要文本列表，格式与日志输出保持一致。

    Args:
        metrics: 账户指标字典

    Returns:
        list[str]: 每行为一个摘要条目
    """
    if not metrics:
        return []
    lines: List[str] = []

    init_assets = metrics.get("init_assets")
    final_assets = metrics.get("final_assets")
    max_stock_count = metrics.get("max_stock_count")
    empty_days = metrics.get("empty_days")
    sample_days = metrics.get("sample_days")

    lines.append("账户分析结果")
    if init_assets is not None:
        lines.append(f"初始资金: {init_assets:,.2f} 元")
    if final_assets is not None:
        lines.append(f"最终资金: {final_assets:,.2f} 元")
    # (显示名, metrics 键, 是否百分比)；键不存在则跳过，兼容旧指标字典。格式化复用 analyze.fmt_metric，与日志口径一致
    for label, key, pct in (
        ("盈利率", "profit_rate", True),
        ("年化收益率", "annual_return", True),
        ("最大回撤", "max_drawdown", True),
        ("年化波动率", "annual_volatility", True),
        ("夏普比率(年化)", "sharpe_ratio", False),
        ("索提诺比率(年化)", "sortino_ratio", False),
        ("卡玛比率", "calmar_ratio", False),
        ("超额年化收益(相对上证)", "excess_return", True),
        ("Beta(相对上证)", "beta", False),
        ("Alpha(年化,相对上证)", "alpha", True),
        ("最大涨幅", "max_profit_rate", True),
        ("最大跌幅", "max_loss_rate", True),
        ("最大仓位资金占用率", "max_position_rate", True),
    ):
        if key in metrics:
            lines.append(f"{label}: {fmt_metric(metrics.get(key), pct=pct)}")
    if max_stock_count is not None:
        lines.append(f"最大持仓股票数: {max_stock_count}")
    if empty_days is not None:
        lines.append(f"空仓天数: {empty_days}")
    if sample_days is not None:
        lines.append(f"有效收益样本天数: {sample_days}")
    if metrics.get("annualized_extrapolated"):
        lines.append(f"⚠️ 样本偏少：年化夏普/收益/波动率为外推结果，仅供参考")
    active_days = metrics.get("active_days")
    risk_basis = metrics.get("risk_metric_basis")
    if risk_basis is not None:
        lines.append(f"风险指标口径: {risk_basis}（active=剔除纯空仓静止日）")
    if active_days is not None:
        lines.append(f"风险样本天数: {active_days}")
    return lines


def _build_stock_summary_from_file(path: str) -> List[str]:
    """
    基于 analyze_transactions_*.xlsx 构造个股分析结果摘要文本列表。

    Args:
        path: analyze_transactions Excel 文件路径

    Returns:
        list[str]: 每行为一个摘要条目
    """
    if not path or not os.path.exists(path):
        return []
    try:
        df = pd.read_excel(path)
    except Exception as exc:  # noqa: BLE001
        error(f"加载个股分析文件失败: {exc}")
        return []
    if df is None or df.empty or "涨跌幅" not in df.columns:
        return []

    # 复用 analyze.py 的交易级汇总，保证前端与回测日志口径一致（净收益、盈亏比除零保护等）
    lines: List[str] = []
    if "是否平仓" in df.columns:
        is_closed = df["是否平仓"].astype(bool)  # Excel 回读可能为 object，统一为 bool
        lines += format_trade_summary(summarize_trades(df[is_closed]), title="个股分析结果（已平仓·净收益口径）")
        if (~is_closed).any():
            lines += format_trade_summary(summarize_trades(df), title="个股分析结果（含未平仓·期末市值）")
    else:
        # 兼容旧版 Excel（无 是否平仓 列）
        lines += format_trade_summary(summarize_trades(df))
    return lines


def _build_run_summaries(files: Dict[str, str], metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    构造单次回测的账户与个股分析摘要。

    Args:
        files: 本次回测生成的结果文件映射
        metrics: 账户指标字典

    Returns:
        dict: {"account": [...], "stock": [...]}
    """
    account_lines = _build_account_summary(metrics)
    analyze_file = files.get("analyze_transactions")
    stock_lines: List[str] = []
    if analyze_file:
        stock_lines = _build_stock_summary_from_file(os.path.join(RESULTS_DIR, analyze_file))
    return {
        "account": account_lines,
        "stock": stock_lines,
    }


app = FastAPI(title="MoneyDog Web", version="0.1.0")

# 允许本机访问，可按需扩展
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载前端构建产物中的哈希资源（仅在 dist 已构建时）
if os.path.isdir(FRONTEND_ASSETS):
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS), name="assets")


@app.get("/api/strategies", response_model=List[StrategyInfo])
async def list_strategies() -> List[StrategyInfo]:
    """
    获取当前项目中可用的策略列表。

    Returns:
        list[StrategyInfo]: 策略模块及其下策略类列表
    """
    app_cfg = ConfigApp()
    raw_list = app_cfg._discover_strategies()  # noqa: SLF001
    return [StrategyInfo(**item) for item in raw_list]


@app.get("/api/config")
async def get_current_config() -> JSONResponse:
    """
    获取当前生效的策略配置与回测配置。

    Returns:
        JSONResponse: 包含 strategy 与 backtest 两部分配置
    """
    cfg = configparser.ConfigParser()
    cfg.read(get_config_path(), encoding="utf-8")

    strategy_cfg = StrategyConfig(
        strategy_module=cfg.get("STRATEGY", "strategy_module", fallback=""),
        strategy_class=cfg.get("STRATEGY", "strategy_class", fallback=""),
    )
    backtest_cfg = _build_default_backtest_config(cfg)

    return JSONResponse(
        {
            "strategy": strategy_cfg.model_dump(),
            "backtest": backtest_cfg.model_dump(),
        },
    )


@app.post("/api/backtests/run")
async def run_backtest(payload: RunBacktestRequest) -> JSONResponse:
    """
    根据前端提交的配置更新 config.ini，并在后台启动一次回测。

    回测逻辑会在独立线程中执行，本接口立即返回回测 ID，用于后续在
    历史回测列表与指标接口中查询结果。

    Args:
        payload: 前端提交的策略与回测配置

    Returns:
        JSONResponse: {\"run_id\": str, \"status\": \"running\"}
    """
    bt = payload.backtest

    # 以磁盘 config.ini 为底，仅在内存中覆盖本次回测字段；不落盘，避免污染用户配置。
    mem_cfg = configparser.ConfigParser()
    mem_cfg.read(get_config_path(), encoding="utf-8")
    if not mem_cfg.has_section("STRATEGY"):
        mem_cfg.add_section("STRATEGY")
    mem_cfg.set("STRATEGY", "strategy_module", payload.strategy.strategy_module)
    mem_cfg.set("STRATEGY", "strategy_class", payload.strategy.strategy_class)
    if not mem_cfg.has_section("BACKTEST"):
        mem_cfg.add_section("BACKTEST")
    # 字段名与 config.ini 键一一对应，逐项写入；bool 需转小写以匹配 configparser 语义。
    for key, value in bt.model_dump().items():
        mem_cfg.set("BACKTEST", key, str(value).lower() if isinstance(value, bool) else str(value))

    strategy_label = _strategy_label(payload.strategy)
    period = f"{bt.backtest_start_time}-{bt.backtest_end_time}"

    # 原子占位：单回测槽位，已有运行则拒绝（409），避免并发提交竞态与内存配置串扰。
    with _RUN_LOCK:
        if CURRENT_BACKTEST.get("run_id"):
            raise HTTPException(status_code=409, detail="已有回测正在运行，请等待其结束或先中止")
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        CURRENT_BACKTEST.update(
            run_id=run_id,
            strategy=None,
            strategy_label=strategy_label,
            started_at=datetime.now().isoformat(timespec="seconds"),
            backtest_period=period,
        )

    # 记录回测前的结果文件快照
    before_snapshot = _snapshot_results_files()

    def _run_task() -> None:
        """
        后台线程实际执行回测任务：安装内存配置、运行策略、分析结果并写入索引。
        """
        strategy_code_filename: Optional[str] = None
        info(f"Web 后台回测开始，run_id={run_id}, strategy={strategy_label}, period={period}")
        start_ts = time.time()
        strategy = None
        status = "failed"
        try:
            # 安装内存覆盖配置（不落盘），驱动本次 load_strategy / run
            set_backtest_config_override(mem_cfg)
            strategy = load_strategy()
            # 为当前策略注入进度回调，用于 Web 前端展示回测/选股进度
            if hasattr(strategy, "set_progress_callback"):
                try:
                    def _progress_callback(stage: str, current: int, total: int) -> None:
                        """
                        回测进度回调：由策略在每日循环或选股过程中调用，更新全局进度状态。

                        Args:
                            stage: 当前阶段标识（如 'selection' 或 'backtest'）。
                            current: 已完成的交易日数量。
                            total: 总交易日数量。
                        """
                        if total <= 0:
                            percent = 0.0
                        else:
                            percent = max(0.0, min(100.0, current / total * 100.0))
                        BACKTEST_PROGRESS["run_id"] = run_id
                        BACKTEST_PROGRESS["stage"] = stage or "backtest"
                        BACKTEST_PROGRESS["current"] = int(current)
                        BACKTEST_PROGRESS["total"] = int(total)
                        BACKTEST_PROGRESS["percent"] = float(percent)

                    strategy.set_progress_callback(_progress_callback)
                except Exception as exc:  # noqa: BLE001
                    error(f"注入回测进度回调失败: {exc}")
            # 回测开始前为本次运行保存一份策略源码快照到 results 目录
            try:
                strategy_module_name = payload.strategy.strategy_module
                src_path = os.path.join(PROJECT_ROOT, "strategys", f"{strategy_module_name}.py")
                if os.path.exists(src_path):
                    strategy_code_filename = f"strategy_{strategy_module_name}_{run_id}.py"
                    dst_path = os.path.join(RESULTS_DIR, strategy_code_filename)
                    shutil.copy2(src_path, dst_path)
                    info(
                        f"已为回测 {run_id} 保存策略源码快照: "
                        f"{strategy_module_name}.py -> {strategy_code_filename}",
                    )
                else:
                    info(
                        "未找到策略源码文件，跳过保存策略代码快照: "
                        f"{src_path}",
                    )
            except Exception as exc:  # noqa: BLE001
                error(f"保存策略源码快照失败: {exc}")
            CURRENT_BACKTEST["strategy"] = strategy
            # 重置并初始化进度信息
            BACKTEST_PROGRESS["run_id"] = run_id
            BACKTEST_PROGRESS["stage"] = "selection"
            BACKTEST_PROGRESS["current"] = 0
            BACKTEST_PROGRESS["total"] = 0
            BACKTEST_PROGRESS["percent"] = 0.0
            strategy.run()
            status = "success"
        except Exception as exc:  # noqa: BLE001
            error(f"Web 后台回测失败: {exc}")
        finally:
            elapsed = time.time() - start_ts
            # 优雅中止会让 run() 正常返回，据策略停止标记归类为 stopped
            if status == "success" and getattr(strategy, "_stop_requested", False):
                status = "stopped"
            info(f"Web 后台回测结束，耗时 {elapsed:.2f} 秒，run_id={run_id}，status={status}")
            # 卸载内存配置覆盖，恢复从 config.ini 读取；清理运行槽位并记录结束态
            clear_backtest_config_override()
            _reset_current_backtest()
            LAST_FINISHED.update(run_id=run_id, status=status)
            # 回测结束后若进度尚未到 100%，则补齐为 100%
            if BACKTEST_PROGRESS.get("run_id") == run_id:
                BACKTEST_PROGRESS["stage"] = "backtest"
                BACKTEST_PROGRESS["percent"] = 100.0

        # 回测完成后，对比结果目录，找出本次新增/更新的文件
        after_snapshot = _snapshot_results_files()
        changed_files = _diff_results_files(before_snapshot, after_snapshot)

        files_map: Dict[str, str] = {}
        position_file: Optional[str] = None
        for name in changed_files:
            lower = name.lower()
            if lower.startswith("account_curve_") and lower.endswith(".png"):
                files_map["account_curve"] = name
            elif lower.startswith("original_transactions_") and lower.endswith(".xlsx"):
                files_map["original_transactions"] = name
            elif lower.startswith("position_and_account_changes_") and lower.endswith(".xlsx"):
                files_map["position_and_account_changes"] = name
                position_file = name
            elif lower.startswith("analyze_transactions_") and lower.endswith(".xlsx"):
                files_map["analyze_transactions"] = name

        # 为本次回测记录策略源码文件名（如存在）
        if strategy_code_filename:
            files_map["strategy_code"] = strategy_code_filename

        # 从账户变动文件中提取账户指标（不再重复生成曲线）
        metrics: Dict[str, Any] = {}
        if position_file:
            position_path = os.path.join(RESULTS_DIR, position_file)
            try:
                df_metrics = analyze_account_changes(
                    position_and_account_changes=None,
                    file_path=position_path,
                    transactions_df=None,
                    save_curve=False,
                )
                metrics = _extract_metrics_from_df(df_metrics)
            except Exception as exc:  # noqa: BLE001
                error(f"分析账户指标失败: {exc}")

        # 将本次运行记录写入索引文件
        records = _load_run_index()
        summary = _build_run_summaries(files_map, metrics)
        record = RunRecord(
            id=run_id,
            created_at=datetime.now().isoformat(timespec="seconds"),
            strategy=payload.strategy,
            backtest=payload.backtest,
            files=files_map,
            metrics=metrics or None,
            summary=summary or None,
        )
        records.append(record)
        _save_run_index(records)

    # 启动后台线程执行回测任务，立即返回 run_id
    thread = threading.Thread(target=_run_task, name=f"backtest-{run_id}", daemon=True)
    thread.start()

    return JSONResponse(
        {
            "run_id": run_id,
            "status": "running",
        },
    )


@app.get("/api/backtests", response_model=List[RunRecord])
async def list_backtests() -> List[RunRecord]:
    """
    获取已记录的历史回测列表。

    Returns:
        list[RunRecord]: 回测记录列表
    """
    return _load_run_index()


@app.get("/api/backtests/status")
async def get_current_backtest_status() -> JSONResponse:
    """
    查询当前回测运行状态。

    Returns:
        JSONResponse: {
            "running": bool,
            "run_id": Optional[str],
            "stage": str,
            "current": int,
            "total": int,
            "percent": float,
        }
    """
    current = CURRENT_BACKTEST
    run_id = current.get("run_id")
    running = bool(run_id)

    # 仅当进度信息与当前运行的回测 ID 一致时，才返回实际进度；否则视为 0。
    if run_id and BACKTEST_PROGRESS.get("run_id") == run_id:
        stage = str(BACKTEST_PROGRESS.get("stage", "idle"))
        progress_current = int(BACKTEST_PROGRESS.get("current", 0) or 0)
        progress_total = int(BACKTEST_PROGRESS.get("total", 0) or 0)
        progress_percent = float(BACKTEST_PROGRESS.get("percent", 0.0) or 0.0)
    else:
        stage = "idle"
        progress_current = 0
        progress_total = 0
        progress_percent = 0.0

    return JSONResponse(
        {
            "running": running,
            "run_id": run_id,
            "stage": stage,
            "current": progress_current,
            "total": progress_total,
            "percent": progress_percent,
            # 运行态恢复用元信息（刷新页面后据此重建“运行中”视图）
            "strategy_label": current.get("strategy_label"),
            "started_at": current.get("started_at"),
            "backtest_period": current.get("backtest_period"),
            # 最近结束的回测，供前端从 running -> finished 自动跳转结果页
            "last_finished_run_id": LAST_FINISHED.get("run_id"),
            "last_status": LAST_FINISHED.get("status"),
        },
    )


@app.post("/api/backtests/stop")
async def stop_current_backtest() -> JSONResponse:
    """
    中止当前正在运行的回测任务。

    注意：采用优雅中止方式，仅设置标记；回测会在当前交易日循环结束后退出。
    """
    current = CURRENT_BACKTEST
    run_id = current.get("run_id")
    strategy = current.get("strategy")
    if not run_id or strategy is None:
        raise HTTPException(status_code=400, detail="当前没有正在运行的回测任务")

    # BaseStrategy 提供 request_stop 方法用于优雅中止
    if hasattr(strategy, "request_stop"):
        try:
            strategy.request_stop()
            info(f"已请求中止回测任务，run_id={run_id}")
            return JSONResponse({"success": True, "run_id": run_id})
        except Exception as exc:  # noqa: BLE001
            error(f"中止回测任务失败: {exc}")
            raise HTTPException(status_code=500, detail="中止回测失败") from exc
    raise HTTPException(status_code=500, detail="当前策略不支持中止回测")


@app.delete("/api/backtests/{run_id}")
async def delete_backtest(run_id: str) -> JSONResponse:
    """
    删除指定回测 ID 的历史记录（仅从索引中移除，不删除实际结果文件）。

    Args:
        run_id: 回测 ID

    Returns:
        JSONResponse: 删除是否成功的结果
    """
    records = _load_run_index()
    remaining = [r for r in records if r.id != run_id]
    if len(remaining) == len(records):
        raise HTTPException(status_code=404, detail="未找到对应回测记录")
    _save_run_index(remaining)
    info(f"已从索引中删除回测记录: run_id={run_id}")
    return JSONResponse({"success": True, "run_id": run_id})


@app.get("/api/backtests/{run_id}", response_model=RunRecord)
async def get_backtest(run_id: str) -> RunRecord:
    """
    获取单条回测记录（供结果页深链加载，避免拉取整个历史列表）。

    Args:
        run_id: 回测 ID

    Returns:
        RunRecord: 对应回测记录
    """
    target = _get_record_or_404(run_id)
    return target


@app.get("/api/backtests/{run_id}/metrics")
async def get_backtest_metrics(run_id: str) -> JSONResponse:
    """
    获取指定回测 ID 的账户指标；如索引中尚无指标，则尝试从结果文件即时计算。

    Args:
        run_id: 回测 ID

    Returns:
        JSONResponse: 账户指标字典
    """
    records = _load_run_index()
    target = next((r for r in records if r.id == run_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="未找到对应回测记录")

    # 若索引中已有指标，直接返回
    if target.metrics:
        return JSONResponse(target.metrics)

    # 尝试从结果文件中即时计算
    position_file = target.files.get("position_and_account_changes")
    if not position_file:
        raise HTTPException(status_code=404, detail="未找到账户变动文件")

    position_path = os.path.join(RESULTS_DIR, position_file)
    try:
        df_metrics = analyze_account_changes(
            position_and_account_changes=None,
            file_path=position_path,
            transactions_df=None,
            save_curve=False,
        )
        metrics = _extract_metrics_from_df(df_metrics)
    except Exception as exc:  # noqa: BLE001
        error(f"即时分析账户指标失败: {exc}")
        raise HTTPException(status_code=500, detail="分析账户指标失败") from exc

    # 更新索引中的指标，方便下次直接读取
    target.metrics = metrics
    _save_run_index(records)

    return JSONResponse(metrics)


@app.get("/api/backtests/{run_id}/trades")
async def get_backtest_trades(run_id: str) -> JSONResponse:
    """
    获取指定回测的交易明细（建仓/清仓成对记录，供前端可排序筛选表格与逐笔钻取）。

    Args:
        run_id: 回测 ID

    Returns:
        JSONResponse: {"trades": [ {code, open_time, open_price, close_time, close_price,
                       net_pct, gross_pct, closed, hold_days, commission, tax, cost, remark}, ... ]}
    """
    target = _get_record_or_404(run_id)

    file_name = target.files.get("analyze_transactions")
    if not file_name:
        raise HTTPException(status_code=404, detail="未找到交易分析文件")
    path = os.path.join(RESULTS_DIR, file_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="交易分析文件不存在")
    try:
        df = pd.read_excel(path)
    except Exception as exc:  # noqa: BLE001
        error(f"读取交易分析文件失败: {exc}")
        raise HTTPException(status_code=500, detail="读取交易分析文件失败") from exc
    return JSONResponse({"trades": _json_safe_records(df, _TRADE_COL_MAP)})


@app.get("/api/backtests/{run_id}/positions")
async def get_backtest_positions(run_id: str) -> JSONResponse:
    """
    获取指定回测的每日持仓/账户时间线（供前端表格展示）。

    Args:
        run_id: 回测 ID

    Returns:
        JSONResponse: {"positions": [ {trade_date, stock_count, stock_cost, stock_value,
                       available_amount, total_assets}, ... ]}
    """
    target = _get_record_or_404(run_id)

    file_name = target.files.get("position_and_account_changes")
    if not file_name:
        raise HTTPException(status_code=404, detail="未找到账户变动文件")
    df = load_account_changes_df(os.path.join(RESULTS_DIR, file_name))
    if df.empty:
        raise HTTPException(status_code=404, detail="账户变动数据为空或字段不全")
    records = _json_safe_records(df)
    for rec in records:
        rec["trade_date"] = _fmt_trade_date(rec.get("trade_date"))
    return JSONResponse({"positions": records})


@app.get("/api/backtests/{run_id}/kline")
async def get_backtest_kline(run_id: str, code: str) -> JSONResponse:
    """
    获取某只个股在本次回测区间的日线 K 线及买卖点标记（供逐笔钻取查看）。

    Args:
        run_id: 回测 ID
        code: 股票代码（如 000001.SZ）

    Returns:
        JSONResponse: {code, period, bars:[{date,open,high,low,close,volume}],
                       markers:[{date,time,action,price,volume,desc}]}
    """
    target = _get_record_or_404(run_id)

    start = target.backtest.backtest_start_time
    end = target.backtest.backtest_end_time
    try:
        bars = get_daily_bars([code], period="1d", start_time=start, end_time=end, table_name="daily_1day")
    except Exception as exc:  # noqa: BLE001
        error(f"获取 K 线失败 code={code}: {exc}")
        raise HTTPException(status_code=500, detail="获取 K 线数据失败") from exc
    bars_json = _bars_to_json(bars.get(code), "1d")

    # 买卖点：从原始成交记录按股票代码过滤
    markers: List[Dict[str, Any]] = []
    ot_file = target.files.get("original_transactions")
    if ot_file:
        ot_path = os.path.join(RESULTS_DIR, ot_file)
        if os.path.exists(ot_path):
            try:
                otdf = pd.read_excel(ot_path)
                sub = otdf[otdf["stock_code"] == code]
                for _, row in sub.iterrows():
                    ts = str(row.get("time_str", ""))
                    markers.append(
                        {
                            "date": ts[:10],
                            "time": ts,
                            "action": str(row.get("action", "")),
                            "price": float(row["price"]),
                            "volume": int(row["volume"]),
                            "desc": str(row.get("desc", "")),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                error(f"读取买卖点失败 code={code}: {exc}")

    return JSONResponse({"code": code, "period": "1d", "bars": bars_json, "markers": markers})


@app.get("/api/backtests/{run_id}/curve.json")
async def get_backtest_curve_json(run_id: str) -> JSONResponse:
    """
    获取指定回测的收益/回撤/仓位时间序列（供前端 ECharts 交互式绘制，替代静态 PNG）。

    Args:
        run_id: 回测 ID

    Returns:
        JSONResponse: dates/equity_pct/drawdown_pct/position_ratio/benchmark_pct/total_assets/initial_amount
    """
    target = _get_record_or_404(run_id)

    position_file = target.files.get("position_and_account_changes")
    if not position_file:
        raise HTTPException(status_code=404, detail="未找到账户变动文件")

    df = load_account_changes_df(os.path.join(RESULTS_DIR, position_file))
    if df.empty:
        raise HTTPException(status_code=404, detail="账户变动数据为空或字段不全")

    initial = float(df.iloc[0]["total_assets"])
    return JSONResponse(compute_account_series(df, initial, include_benchmark=True))


@app.get("/api/backtests/{run_id}/curve")
async def get_backtest_curve(run_id: str) -> FileResponse:
    """
    获取指定回测 ID 的账户曲线 PNG 文件。

    Args:
        run_id: 回测 ID

    Returns:
        FileResponse: PNG 图片响应
    """
    records = _load_run_index()
    target = next((r for r in records if r.id == run_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="未找到对应回测记录")

    curve_file = target.files.get("account_curve")
    if not curve_file:
        raise HTTPException(status_code=404, detail="未找到账户曲线文件")

    curve_path = os.path.join(RESULTS_DIR, curve_file)
    if not os.path.exists(curve_path):
        raise HTTPException(status_code=404, detail="账户曲线文件不存在")

    return FileResponse(curve_path, media_type="image/png")


@app.get("/api/backtests/{run_id}/record")
async def get_backtest_record(run_id: str) -> FileResponse:
    """
    获取指定回测 ID 对应的主要记录 Excel 文件。

    优先返回交易分析文件 analyze_transactions_*.xlsx，
    若不存在则退回到原始成交 original_transactions_*.xlsx，
    再退回到账户变动 position_and_account_changes_*.xlsx。
    """
    records = _load_run_index()
    target = next((r for r in records if r.id == run_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="未找到对应回测记录")

    file_name = (
        target.files.get("analyze_transactions")
        or target.files.get("original_transactions")
        or target.files.get("position_and_account_changes")
    )
    if not file_name:
        raise HTTPException(status_code=404, detail="未找到任何记录文件")

    record_path = os.path.join(RESULTS_DIR, file_name)
    if not os.path.exists(record_path):
        raise HTTPException(status_code=404, detail="记录文件不存在")

    return FileResponse(
        record_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=file_name,
    )


@app.get("/api/backtests/{run_id}/code")
async def get_backtest_code(run_id: str) -> JSONResponse:
    """
    获取指定回测 ID 对应的策略源码内容。

    若索引中未记录策略源码文件，或文件已不存在，则返回 404。

    Args:
        run_id: 回测 ID

    Returns:
        JSONResponse: {\"file_name\": str, \"code\": str}
    """
    records = _load_run_index()
    target = next((r for r in records if r.id == run_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="未找到对应回测记录")

    code_file = target.files.get("strategy_code")
    if not code_file:
        raise HTTPException(status_code=404, detail="未找到策略源码文件记录")

    code_path = os.path.join(RESULTS_DIR, code_file)
    if not os.path.exists(code_path):
        raise HTTPException(status_code=404, detail="策略源码文件不存在")

    try:
        with open(code_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as exc:  # noqa: BLE001
        error(f"读取策略源码文件失败: {exc}")
        raise HTTPException(status_code=500, detail="读取策略源码失败") from exc

    return JSONResponse(
        {
            "file_name": code_file,
            "code": content,
        },
    )


@app.get("/api/market/bars")
async def get_market_bars(
    code: str,
    period: str = "1d",
    start: str = "",
    end: str = "",
    market: str = "stock",
) -> JSONResponse:
    """
    获取个股/指数行情 K 线（供行情浏览与 K 线钻取共用）。

    Args:
        code: 代码（个股如 000001.SZ；指数如 000001.SH 且 market=index）
        period: '1d' 或 '1m'
        start/end: YYYYMMDD 起止（分钟线要求 start==end 单日，限制数据量）
        market: 'stock'（默认）或 'index'

    Returns:
        JSONResponse: {code, period, bars:[{date,open,high,low,close,volume}]}
    """
    if period not in ("1d", "1m"):
        raise HTTPException(status_code=422, detail="period 仅支持 1d 或 1m")
    if period == "1m" and (not start or start != end):
        raise HTTPException(status_code=422, detail="分钟线请指定同一天（start==end）以限制数据量")

    if market == "index":
        table = "index_daily"
    else:
        table = "daily_1day" if period == "1d" else "daily_1min"
    try:
        bars = get_daily_bars([code], period=period, start_time=start, end_time=end, table_name=table)
    except Exception as exc:  # noqa: BLE001
        error(f"获取行情失败 code={code}: {exc}")
        raise HTTPException(status_code=500, detail="获取行情数据失败") from exc
    return JSONResponse({"code": code, "period": period, "bars": _bars_to_json(bars.get(code), period)})


# 全市场股票代码缓存（首次查询后复用，避免每次扫描 stock_list 表）
_STOCK_CODES_CACHE: List[str] = []
# 整体数据覆盖缓存（进程内行情数据静态，避免每次仪表盘请求全表聚合）
_COVERAGE_CACHE: Optional[Dict[str, Any]] = None
# 候选指数（代码 -> 中文名），实际是否可用由 has_index_1day_data 校验
_INDEX_CANDIDATES = {
    "000001.SH": "上证指数",
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
}


def _get_stock_codes() -> List[str]:
    """惰性获取并缓存全市场股票代码（首次查询扫描 stock_list）。"""
    global _STOCK_CODES_CACHE  # noqa: PLW0603
    if not _STOCK_CODES_CACHE:
        _STOCK_CODES_CACHE = get_stock_list_in_sector("")
    return _STOCK_CODES_CACHE


def _get_overall_coverage_cached() -> Dict[str, Any]:
    """惰性获取并缓存整体数据覆盖（全表聚合较重，进程内复用）。"""
    global _COVERAGE_CACHE  # noqa: PLW0603
    if _COVERAGE_CACHE is None:
        _COVERAGE_CACHE = get_overall_coverage()
    return _COVERAGE_CACHE


def _run_brief(record: RunRecord) -> Dict[str, Any]:
    """提取回测记录的总览简报字段。"""
    m = record.metrics or {}
    return {
        "id": record.id,
        "created_at": record.created_at,
        "strategy_label": _strategy_label(record.strategy),
        "profit_rate": m.get("profit_rate"),
        "max_drawdown": m.get("max_drawdown"),
        "sharpe_ratio": m.get("sharpe_ratio"),
    }


@app.get("/api/dashboard")
async def get_dashboard() -> JSONResponse:
    """
    总览仪表盘聚合：回测总数、运行态、最近回测、最优（夏普）回测、数据覆盖。

    Returns:
        JSONResponse: {total_runs, running, active_run_id, recent[], best_by_sharpe, data{...}}
    """
    records = _load_run_index()
    recent = [_run_brief(r) for r in reversed(records[-8:])]

    # 夏普最高的回测（有 sharpe 指标者）
    best = None
    best_sharpe = None
    for r in records:
        s = (r.metrics or {}).get("sharpe_ratio")
        if isinstance(s, (int, float)) and (best_sharpe is None or s > best_sharpe):
            best_sharpe = s
            best = _run_brief(r)

    try:
        stock_count = len(_get_stock_codes())
    except Exception as exc:  # noqa: BLE001
        error(f"获取股票列表失败: {exc}")
        stock_count = 0

    coverage = _get_overall_coverage_cached()
    return JSONResponse(
        {
            "total_runs": len(records),
            "running": bool(CURRENT_BACKTEST.get("run_id")),
            "active_run_id": CURRENT_BACKTEST.get("run_id"),
            "recent": recent,
            "best_by_sharpe": best,
            "data": {
                "stock_count": stock_count,
                "daily_start": coverage.get("start"),
                "daily_end": coverage.get("end"),
                "trade_days": coverage.get("trade_days"),
            },
        }
    )


@app.get("/api/market/stocks")
async def list_market_stocks(q: str = "", limit: int = 50) -> JSONResponse:
    """
    列出可浏览的股票代码（支持前缀/子串过滤）。stock_list 仅有代码、无名称。

    Args:
        q: 代码过滤关键字（子串匹配）
        limit: 返回上限，默认 50

    Returns:
        JSONResponse: {"stocks": [{"code": ...}, ...], "total": 匹配总数}
    """
    try:
        codes = _get_stock_codes()
    except Exception as exc:  # noqa: BLE001
        error(f"获取股票列表失败: {exc}")
        raise HTTPException(status_code=500, detail="获取股票列表失败") from exc
    kw = q.strip().upper()
    matched = [c for c in codes if kw in c.upper()] if kw else codes
    return JSONResponse({"stocks": [{"code": c} for c in matched[:limit]], "total": len(matched)})


@app.get("/api/market/indices")
async def list_market_indices() -> JSONResponse:
    """
    列出数据库中可用的指数（在候选集中且 index_daily 有数据）。

    Returns:
        JSONResponse: {"indices": [{"code": ..., "name": ...}, ...]}
    """
    indices = [
        {"code": code, "name": name}
        for code, name in _INDEX_CANDIDATES.items()
        if has_index_1day_data(code)
    ]
    return JSONResponse({"indices": indices})


@app.get("/api/market/coverage")
async def get_market_coverage(code: str, market: str = "stock") -> JSONResponse:
    """
    获取指定代码的数据覆盖（起止日期、条数），供行情浏览展示。

    Args:
        code: 代码
        market: 'stock' 或 'index'

    Returns:
        JSONResponse: {"daily": {start,end,count}, "minute": {start,end,count}|null}
    """
    try:
        return JSONResponse(get_data_coverage(code, market=market))
    except Exception as exc:  # noqa: BLE001
        error(f"获取数据覆盖失败 code={code}: {exc}")
        raise HTTPException(status_code=500, detail="获取数据覆盖失败") from exc


# dist 未构建时的兜底提示页（保证纯 Python 环境也能启动并给出指引）
_DEV_FALLBACK_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>MoneyDog</title></head>
<body style="font-family:-apple-system,Segoe UI,sans-serif;background:#0b1220;color:#e2e8f0;padding:48px;line-height:1.8">
<h1 style="color:#22c55e">MoneyDog 量化交易平台</h1>
<p>前端尚未构建。请任选其一：</p>
<ul>
<li>开发模式：<code>cd web/frontend &amp;&amp; npm install &amp;&amp; npm run dev</code>，然后访问 <a style="color:#4ade80" href="http://127.0.0.1:5173">http://127.0.0.1:5173</a>（已代理 /api）。</li>
<li>生产模式：<code>cd web/frontend &amp;&amp; npm run build</code> 生成 dist 后刷新本页。</li>
</ul>
</body></html>"""


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """
    SPA 兜底路由：非 /api、非 /assets 的路径一律返回前端入口 index.html，
    以支持 /runs/:id、/market 等前端深链在刷新时正常加载。

    Args:
        full_path: 捕获的完整路径（不含前导斜杠）

    Returns:
        FileResponse: 已构建时返回 dist/index.html；否则返回构建指引兜底页
    """
    # /api 前缀交由真实 API 路由处理；能落到此处说明该 API 不存在，返回 404 而非 index.html
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    if os.path.exists(FRONTEND_INDEX):
        return FileResponse(FRONTEND_INDEX, media_type="text/html")
    return HTMLResponse(_DEV_FALLBACK_HTML)


def get_app() -> FastAPI:
    """
    供 Uvicorn 等服务器调用的应用工厂函数。

    Returns:
        FastAPI: MoneyDog Web 应用实例
    """
    return app


if __name__ == "__main__":
    # 允许直接通过 python -m web.server 启动开发服务器
    import uvicorn

    # 不启用 reload：utils.data 在模块导入时即打开 DuckDB 连接，reload 的
    # 监听子进程会二次导入并与主进程争抢同一数据库文件锁而启动失败。
    uvicorn.run(app, host="127.0.0.1", port=8000)

