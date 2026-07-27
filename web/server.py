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
from utils.logger import error, info
from laboratory.analyze import (
    analyze_account_changes,
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

# 当前正在后台运行的回测任务信息（用于中止回测）
CURRENT_BACKTEST: Dict[str, Any] = {
    "run_id": None,
    "strategy": None,
}

# 当前回测进度信息（供前端查询进度展示）
BACKTEST_PROGRESS: Dict[str, Any] = {
    "run_id": None,
    "stage": "idle",  # idle/selection/backtest
    "current": 0,
    "total": 0,
    "percent": 0.0,
}


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


def _load_run_index() -> List[RunRecord]:
    """
    加载 run_index.json 中的所有回测记录。

    Returns:
        list[RunRecord]: 回测记录列表
    """
    _ensure_results_dir()
    if not os.path.exists(RUN_INDEX_PATH):
        return []
    try:
        with open(RUN_INDEX_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [RunRecord(**item) for item in raw]
    except Exception as exc:  # noqa: BLE001
        error(f"加载回测索引失败: {exc}")
        return []


def _save_run_index(records: List[RunRecord]) -> None:
    """
    将回测记录列表写入 run_index.json。

    Args:
        records: 回测记录列表
    """
    _ensure_results_dir()
    try:
        payload = [record.model_dump() for record in records]
        with open(RUN_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        error(f"保存回测索引失败: {exc}")


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


def _extract_metrics_from_df(df: pd.DataFrame) -> Dict[str, Any]:
    """
    将 analyze_account_changes 返回的单行 DataFrame 转换为 dict。

    Args:
        df: 账户分析结果 DataFrame

    Returns:
        dict: 账户指标字典
    """
    if df is None or df.empty:
        return {}
    row = df.iloc[0].to_dict()
    # 确保 JSON 可序列化（numpy 类型转原生类型；NaN 统一转 None 以产出合法 JSON）
    result: Dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (pd.Timestamp, datetime)):
            result[key] = value.isoformat()
            continue
        if hasattr(value, "item"):
            value = value.item()
        result[key] = None if isinstance(value, float) and pd.isna(value) else value
    return result


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
    cfg.read(os.path.join(PROJECT_ROOT, "config.ini"), encoding="utf-8")

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
    config_path = os.path.join(PROJECT_ROOT, "config.ini")
    cfg = configparser.ConfigParser()
    cfg.read(config_path, encoding="utf-8")

    # 更新策略配置
    if not cfg.has_section("STRATEGY"):
        cfg.add_section("STRATEGY")
    cfg.set("STRATEGY", "strategy_module", payload.strategy.strategy_module)
    cfg.set("STRATEGY", "strategy_class", payload.strategy.strategy_class)

    # 更新回测配置
    if not cfg.has_section("BACKTEST"):
        cfg.add_section("BACKTEST")
    bt = payload.backtest
    cfg.set("BACKTEST", "backtest_start_time", bt.backtest_start_time)
    cfg.set("BACKTEST", "backtest_end_time", bt.backtest_end_time)
    cfg.set("BACKTEST", "initial_amount", str(bt.initial_amount))
    cfg.set("BACKTEST", "commission_rate", str(bt.commission_rate))
    cfg.set("BACKTEST", "min_commission", str(bt.min_commission))
    cfg.set("BACKTEST", "tax_rate", str(bt.tax_rate))
    cfg.set("BACKTEST", "limit_vol_type", bt.limit_vol_type)
    cfg.set("BACKTEST", "max_vol_rate", str(bt.max_vol_rate))
    cfg.set("BACKTEST", "max_vol_amount", str(bt.max_vol_amount))
    cfg.set(
        "BACKTEST",
        "batch_stock_selection_use_threads",
        str(bt.batch_stock_selection_use_threads).lower(),
    )
    cfg.set(
        "BACKTEST",
        "batch_stock_selection_threads",
        str(bt.batch_stock_selection_threads),
    )

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            cfg.write(f)
    except Exception as exc:  # noqa: BLE001
        error(f"写入配置文件失败: {exc}")
        raise HTTPException(status_code=500, detail="保存配置失败") from exc

    # 记录回测前的结果文件快照
    before_snapshot = _snapshot_results_files()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _run_task() -> None:
        """
        后台线程实际执行回测任务：运行策略、分析结果并写入索引。
        """
        global CURRENT_BACKTEST  # noqa: PLW0603
        strategy_code_filename: Optional[str] = None
        info(
            f"Web 后台回测开始，run_id={run_id}, "
            f"strategy={payload.strategy.strategy_module}.{payload.strategy.strategy_class}, "
            f"period={bt.backtest_start_time}-{bt.backtest_end_time}",
        )
        start_ts = time.time()
        strategy = None
        try:
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
            CURRENT_BACKTEST = {"run_id": run_id, "strategy": strategy}
            # 重置并初始化进度信息
            BACKTEST_PROGRESS["run_id"] = run_id
            BACKTEST_PROGRESS["stage"] = "selection"
            BACKTEST_PROGRESS["current"] = 0
            BACKTEST_PROGRESS["total"] = 0
            BACKTEST_PROGRESS["percent"] = 0.0
            strategy.run()
        except Exception as exc:  # noqa: BLE001
            error(f"Web 后台回测失败: {exc}")
        finally:
            elapsed = time.time() - start_ts
            info(f"Web 后台回测结束，耗时 {elapsed:.2f} 秒，run_id={run_id}")
            # 清理当前运行状态
            CURRENT_BACKTEST = {"run_id": None, "strategy": None}
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

    uvicorn.run(
        "web.server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )

