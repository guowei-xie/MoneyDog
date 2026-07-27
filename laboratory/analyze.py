"""
分析工具库
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 使用支持中文的字体，避免 DejaVu Sans 缺失 CJK 字形警告（macOS 常用苹方/黑体）
plt.rcParams["font.sans-serif"] = ["PingFang SC", "Heiti SC", "STHeiti", "Arial Unicode MS", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from utils.util import time_str_to_datetime, get_date_interval, get_trade_days_interval
from utils.logger import info
from utils.data import get_trade_calendar, get_daily_bars
from utils.backtest_config import get_metrics_params, get_backtest_end_time, get_risk_metric_basis
from laboratory.metrics import build_risk_return_series, compute_return_risk_metrics

# 账户变动分析必要列
REQ_COLS_ACCOUNT = ["trade_date", "total_assets", "stock_count", "stock_value"]

# 年化外推提示阈值：有效样本天数低于此值时，年化夏普/收益/波动率为外推结果，仅供参考
EXTRAPOLATION_MIN_SAMPLE = 60


def fmt_metric(v, pct: bool = False, nd: int = 4) -> str:
    """
    统一格式化评价指标：None/NaN → '无法计算'，否则按百分比或定点小数渲染。
    供日志（analyze）与 Web 摘要（server）共用，避免两处格式化口径漂移。
    """
    if v is None or not pd.notnull(v):
        return "无法计算"
    return f"{v * 100:.2f}%" if pct else f"{v:.{nd}f}"


def summarize_trades(df: pd.DataFrame, rate_col: str = "涨跌幅") -> dict:
    """
    对交易明细汇总胜率/盈亏比等交易级指标，供日志与 Web 前端共用（消除口径漂移）。
    收益率列默认取 `涨跌幅`（净收益口径）。分母做除零/空集保护，无亏损交易时盈亏比返回 None。
    Args:
        df: 交易明细 DataFrame
        rate_col: 收益率列名，默认 '涨跌幅'
    Returns:
        dict: 汇总指标；df 为空或缺列时返回 {}
    """
    if df is None or df.empty or rate_col not in df.columns:
        return {}
    rates = df[rate_col]
    total = len(df)
    win_mask = rates > 0
    loss_mask = rates < 0
    avg_profit = rates[win_mask].mean() * 100 if win_mask.any() else 0.0
    avg_loss = rates[loss_mask].mean() * 100 if loss_mask.any() else 0.0
    # 盈亏比 = 平均盈利 / |平均亏损|；无亏损交易时无法定义，返回 None（避免 NaN/除零）
    profit_loss_ratio = (-avg_profit / avg_loss) if avg_loss != 0 else None
    summary = {
        "total_trades": total,
        "win_rate": win_mask.sum() / total * 100,
        "avg_change": rates.mean() * 100,
        "max_change": rates.max() * 100,
        "min_change": rates.min() * 100,
        "avg_profit": avg_profit,
        "avg_loss": avg_loss,
        "profit_loss_ratio": profit_loss_ratio,
        "total_sum": rates.sum() * 100,
    }
    if "持仓天数" in df.columns:
        summary["avg_hold_days"] = df["持仓天数"].mean()
    for col, key in (("总手续费", "total_commission"), ("总印花税", "total_tax"), ("总成本", "total_costs")):
        if col in df.columns:
            summary[key] = df[col].sum()
    return summary


def format_trade_summary(summary: dict, title: str = "个股分析结果") -> list:
    """
    将 summarize_trades 的结果格式化为展示文本行，日志与 Web 前端共用以保证口径一致。
    Args:
        summary: summarize_trades 返回的字典
        title: 摘要标题
    Returns:
        list[str]: 每行一个摘要条目；summary 为空时返回 []
    """
    if not summary:
        return []
    lines = [title]
    lines.append(f"总交易次数: {summary['total_trades']}")
    lines.append(f"胜率: {summary['win_rate']:.2f}%")
    lines.append(f"平均涨跌幅: {summary['avg_change']:.2f}%")
    lines.append(f"最大涨跌幅: {summary['max_change']:.2f}%")
    lines.append(f"最小涨跌幅: {summary['min_change']:.2f}%")
    lines.append(f"盈亏和: {summary['total_sum']:.2f}%")
    plr = summary.get("profit_loss_ratio")
    plr_str = f"{plr:.2f}" if plr is not None else "无亏损交易，无法计算"
    lines.append(
        f"盈亏比：平均涨幅{summary['avg_profit']:.2f}%，平均跌幅{summary['avg_loss']:.2f}%，盈亏比{plr_str}"
    )
    if "avg_hold_days" in summary:
        lines.append(f"平均持仓天数: {summary['avg_hold_days']:.2f}")
    if "total_commission" in summary:
        lines.append(f"总交易手续费: {summary['total_commission']:,.2f} 元")
    if "total_tax" in summary:
        lines.append(f"总交易印花税: {summary['total_tax']:,.2f} 元")
    if "total_costs" in summary:
        lines.append(f"总交易成本: {summary['total_costs']:,.2f} 元")
    return lines


def _safe_hold_days(close_date8: str, build_date8: str, trade_calendar: list):
    """基于交易日历计算持仓交易日数；日期不在日历内时返回 np.nan 而非抛异常。"""
    try:
        return get_trade_days_interval(close_date8, build_date8, trade_calendar)
    except ValueError:
        return np.nan


def _get_last_closes(codes: list, start_time: str, end_time: str) -> dict:
    """
    批量取多只股票在 [start_time, end_time] 内最后一个交易日的收盘价及日期，用于期末未平仓市值估算。

    一次查询覆盖全部 codes（替代逐仓查库的 N 次往返）。因返回的是各股票 <= end_time 的
    最近一根日线，与按各自建仓日为下界逐仓取"最后一根"结果一致（建仓当日必有日线，故最近一根相同）。

    Returns:
        dict: {code: (last_close 收盘价, last_date8 'YYYYMMDD')}；无数据的 code 不在字典中。
    """
    result: dict = {}
    if not codes:
        return result
    try:
        bars = get_daily_bars(
            stock_list=list(codes), period="1d", start_time=start_time, end_time=end_time, count=1
        )
        for code, bdf in bars.items():
            if bdf is not None and not bdf.empty and "close" in bdf.columns:
                result[code] = (float(bdf["close"].iloc[-1]), str(bdf.index[-1]))
    except Exception as e:
        info(f"未平仓市值估算：批量取价失败 ({e})")
    return result


def minute_k_count_to_time(k_count: int) -> str:
    """
    将当日分时K线数量（1~240）转换为A股交易时间字符串。
    规则：上午 9:30-11:30 共120根，下午 13:00-15:00 共120根；
    第n根对应该分钟结束时刻，如第30根即10:00，第240根即15:00。
    Args:
        k_count: 当日累计分时K线数量（1-240）
    Returns:
        str: 时间字符串 "HH:MM"，超出范围则返回 "HH:MM" 边界值
    """
    k_count = max(1, min(240, int(k_count)))
    if k_count <= 120:
        # 上午：9:30 + k_count 分钟
        total_minutes = 9 * 60 + 30 + k_count
    else:
        # 下午：13:00 + (k_count - 120) 分钟
        total_minutes = 13 * 60 + (k_count - 120)
    h, m = divmod(total_minutes, 60)
    return f"{h:02d}:{m:02d}"


def _trade_date_to_yyyymmdd(val) -> str:
    """将 trade_date 转为 YYYYMMDD 字符串，兼容 int/str/datetime。"""
    if pd.isna(val):
        return ""
    s = str(val).replace("-", "")[:8]
    if len(s) == 8 and s.isdigit():
        return s
    try:
        return pd.to_datetime(val).strftime("%Y%m%d")
    except Exception:
        return ""


def _compute_index_profit_rates(
    df: pd.DataFrame,
    index_code: str = "000001.SH",
) -> Optional[np.ndarray]:
    """
    根据账户回测日期范围，从 index_daily 表取指数日线，计算相对首日的累计盈利率（与账户曲线同横轴天数对齐）。
    Args:
        df: 账户变动 DataFrame，含 trade_date，已按 trade_date 排序
        index_code: 指数代码，默认上证指数 000001.SH
    Returns:
        与 df 行数一致的盈利率数组（%），失败或无数据时返回 None
    """
    if df is None or df.empty or "trade_date" not in df.columns:
        return None
    start_date = _trade_date_to_yyyymmdd(df["trade_date"].iloc[0])
    end_date = _trade_date_to_yyyymmdd(df["trade_date"].iloc[-1])
    if not start_date or not end_date:
        info("指数曲线：trade_date 格式异常，已跳过")
        return None
    try:
        index_bars = get_daily_bars(
            stock_list=[index_code],
            period="1d",
            start_time=start_date,
            end_time=end_date,
            table_name="index_daily",
            count=-1,
        )
        if not index_bars:
            info("指数曲线：index_daily 无数据，已跳过")
            return None
        # 不依赖 code 键格式，取第一个指数（只查了一只时即为该只）
        index_df = next(iter(index_bars.values()))
        if index_df is None or index_df.empty or "close" not in index_df.columns:
            info("指数曲线：指数表无 close 或为空，已跳过")
            return None
        # 去重：同一天多条时取第一条；索引统一为 YYYYMMDD 字符串便于对齐
        close_series = index_df["close"].copy()
        close_series.index = close_series.index.astype(str).str.replace("-", "", regex=False)
        if close_series.index.duplicated().any():
            close_series = close_series[~close_series.index.duplicated(keep="first")]
        # 账户每个交易日对应的 YYYYMMDD
        trade_dates_str = [_trade_date_to_yyyymmdd(t) for t in df["trade_date"]]
        trade_dates_str = [t for t in trade_dates_str if t]
        if len(trade_dates_str) != len(df):
            info("指数曲线：部分 trade_date 无法解析，已跳过")
            return None
        # 用 reindex 按账户日期对齐，缺失用前后填充
        aligned = close_series.reindex(trade_dates_str)
        aligned = aligned.ffill().bfill()
        if aligned.isna().all() or aligned.iloc[0] <= 0:
            info("指数曲线：对齐后无有效收盘价，已跳过")
            return None
        first_close = float(aligned.iloc[0])
        return ((aligned.values / first_close) - 1) * 100
    except Exception as e:
        info(f"指数曲线：获取失败 ({e})，已跳过")
        return None


def load_account_changes_df(file_path: str) -> pd.DataFrame:
    """
    加载账户变动明细 Excel 并做标准化（去空 trade_date、按 trade_date 升序）。

    Args:
        file_path: position_and_account_changes_*.xlsx 路径

    Returns:
        pd.DataFrame: 规范化后的账户变动表；文件缺失/字段不全时返回空 DataFrame
    """
    if not file_path or not os.path.exists(file_path):
        return pd.DataFrame()
    try:
        df = pd.read_excel(file_path)
    except Exception as e:  # noqa: BLE001
        info(f"无法加载账户变动文件: {e}")
        return pd.DataFrame()
    if df is None or df.empty or not all(col in df.columns for col in REQ_COLS_ACCOUNT):
        return pd.DataFrame()
    df = df[df["trade_date"].notna()].sort_values("trade_date").reset_index(drop=True)
    return df


def compute_account_series(
    df: pd.DataFrame,
    initial_assets: float,
    include_benchmark: bool = False,
) -> dict:
    """
    从账户变动表计算收益/回撤/仓位等时间序列（JSON 友好，PNG 与 Web 曲线共用，避免口径漂移）。

    Args:
        df: 含 trade_date、total_assets、stock_value 的账户变动表，已按 trade_date 升序
        initial_assets: 初始资金（与 PNG 口径一致，通常取首日 total_assets）
        include_benchmark: 是否附带上证指数基准累计收益（需查询 index_daily）

    Returns:
        dict: dates / equity_pct / drawdown_pct / position_ratio / total_assets /
              initial_amount（include_benchmark=True 时附带 benchmark_pct，可能为 None）
    """
    total = df["total_assets"].astype(float)
    equity_pct = (total / initial_assets - 1) * 100
    roll_max = total.cummax()
    drawdown_pct = (total / roll_max - 1) * 100
    # 持仓比例 = 持仓价值 / 账户总金额，总金额<=0 时记为 0
    safe_total = total.where(total > 0)
    position_ratio = (df["stock_value"].astype(float) / safe_total).fillna(0.0)

    def _round(series: pd.Series, ndigits: int) -> list:
        return [round(float(v), ndigits) for v in series.tolist()]

    dates = [_trade_date_to_yyyymmdd(t) for t in df["trade_date"]]
    dates_iso = [f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d for d in dates]

    result = {
        "dates": dates_iso,
        "equity_pct": _round(equity_pct, 4),
        "drawdown_pct": _round(drawdown_pct, 4),
        "position_ratio": _round(position_ratio, 6),
        "total_assets": _round(total, 2),
        "initial_amount": float(initial_assets),
    }
    if include_benchmark:
        bench = _compute_index_profit_rates(df)
        result["benchmark_pct"] = (
            [round(float(v), 4) for v in bench] if bench is not None and len(bench) == len(df) else None
        )
    return result


def plot_account_profit_curve(
    df: pd.DataFrame,
    initial_assets: float,
    save_path: str = None,
    transactions_df: pd.DataFrame = None,
    index_profit_rates=None,
) -> str:
    """
    绘制账户分析图：上为账户累计盈利率曲线，中为持仓比例折线图；若有交易记录则下为按买入日的个股盈利率散点及中位数折线。
    Args:
        df: 含 trade_date、total_assets、stock_value 的账户变动 DataFrame，已按 trade_date 排序
        initial_assets: 初始资金
        save_path: 图片保存路径，为空则自动生成到 results/ 下
        transactions_df: 可选，建仓/清仓分析结果，需含 建仓时间、涨跌幅；传入且非空时绘制第三图
        index_profit_rates: 可选，预先算好的指数累计盈利率数组；传入则复用，避免重复查询指数日线
    Returns:
        str: 实际保存的文件路径，未保存则返回空字符串
    """
    if df is None or df.empty or not initial_assets:
        return ""
    days = np.arange(1, len(df) + 1)
    # 收益率与持仓比例与 Web 曲线共用同一口径，避免 PNG/JSON 漂移
    series = compute_account_series(df, initial_assets)
    profit_rates = np.asarray(series["equity_pct"], dtype=float)
    position_ratio = np.asarray(series["position_ratio"], dtype=float)

    has_tx = (
        transactions_df is not None
        and not transactions_df.empty
        and "建仓时间" in transactions_df.columns
        and "涨跌幅" in transactions_df.columns
    )
    tx_mapped = None
    if has_tx:
        # 将买入日期映射为与账户曲线一致的「天数」（统一用 _trade_date_to_yyyymmdd 对齐）
        date_to_day = {_trade_date_to_yyyymmdd(t): i + 1 for i, t in enumerate(df["trade_date"])}
        tx_mapped = transactions_df.copy()
        tx_mapped["_day"] = tx_mapped["建仓时间"].map(lambda t: date_to_day.get(_trade_date_to_yyyymmdd(t), np.nan))
        tx_mapped = tx_mapped.dropna(subset=["_day"])
        if tx_mapped.empty:
            has_tx = False
            tx_mapped = None
    nrows = 3 if has_tx else 2
    # 使用更宽的画布比例，尽量填满 Web 前端横向区域
    fig, axes = plt.subplots(nrows, 1, figsize=(18, 3.6 * nrows), sharex=True)
    if nrows == 2:
        ax1, ax2 = axes
    else:
        ax1, ax2, ax3 = axes

    # 统一语义：颜色/线型在所有子图中含义保持一致
    # - 账户：蓝色实线
    # - 指数：橙色虚线
    # - 中位数：红色实线
    # - 散点：紫色（点）
    # - 持仓比例：绿色实线
    _C_ACCOUNT = "#2563eb"
    _C_INDEX = "#ea580c"
    _C_MEDIAN = "#dc2626"
    _C_SCATTER = "#7c3aed"
    _C_POSITION = "#059669"
    _C_ZERO = "#94a3b8"
    _LS_SOLID = "-"
    _LS_DASH = "--"

    _fmt_pct1 = plt.FuncFormatter(lambda x, _: f"{x:.1f}%")
    _fmt_pct0 = plt.FuncFormatter(lambda x, _: f"{x:.0%}")

    def _style_ax(ax, xlabel=None, ylabel=None, title=None, yformatter=None, ylim=None):
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=11)
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=11)
        if title:
            ax.set_title(title, fontsize=13)
        if ylim is not None:
            ax.set_ylim(ylim)
        if yformatter is not None:
            ax.yaxis.set_major_formatter(yformatter)
        ax.legend(loc="best", fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis="both", labelsize=9)

    # 图1：账户累计盈利率曲线，叠加指数盈利率曲线（相对首日）；调用方可传入以复用，避免重复查询
    if index_profit_rates is None:
        index_profit_rates = _compute_index_profit_rates(df)
    ax1.plot(days, profit_rates, color=_C_ACCOUNT, linestyle=_LS_SOLID, linewidth=1.5, label="账户累计盈利率")
    if index_profit_rates is not None:
        ax1.plot(
            days,
            index_profit_rates,
            color=_C_INDEX,
            linestyle=_LS_DASH,
            linewidth=1.5,
            label="指数累计盈利率",
        )
    ax1.axhline(y=0, color=_C_ZERO, linestyle=_LS_DASH, linewidth=0.8)
    _style_ax(ax1, ylabel="账户累计盈利率 (%)", title="账户累计盈利率曲线", yformatter=_fmt_pct1)
    # 图2：持仓比例折线图
    ax2.plot(days, position_ratio, color=_C_POSITION, linestyle=_LS_SOLID, linewidth=1.5, label="持仓比例")
    _style_ax(ax2, xlabel="天数" if nrows == 2 else None, ylabel="持仓比例", title="持仓比例", yformatter=_fmt_pct0, ylim=(-0.05, 1.05))

    if has_tx and tx_mapped is not None:
        day_index = tx_mapped["_day"].astype(int).values
        y_rates = tx_mapped["涨跌幅"].values * 100
        # 叠加指数曲线：与图1保持同样含义（橙色虚线）
        if index_profit_rates is not None:
            ax3.plot(
                days,
                index_profit_rates,
                color=_C_INDEX,
                linestyle=_LS_DASH,
                linewidth=1.5,
                label="指数累计盈利率",
                zorder=1,
            )
        ax3.scatter(day_index, y_rates, alpha=0.6, s=28, color=_C_SCATTER, label="个股盈利率", zorder=3)
        ax3.axhline(y=0, color=_C_ZERO, linestyle=_LS_DASH, linewidth=0.8)
        median_by_day = tx_mapped.groupby("_day")["涨跌幅"].median().sort_index()
        if not median_by_day.empty:
            ax3.plot(
                median_by_day.index.values,
                median_by_day.values * 100,
                color=_C_MEDIAN,
                linestyle=_LS_SOLID,
                linewidth=2,
                label="盈利率中位数",
                zorder=4,
            )
        _style_ax(ax3, xlabel="天数", ylabel="个股盈利率 (%)", title="按买入日个股盈利率（散点）与中位数折线", yformatter=_fmt_pct1)

    plt.tight_layout()

    if not save_path:
        Path("results").mkdir(parents=True, exist_ok=True)
        save_path = f"results/account_curve_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    return save_path


def analyze_account_changes(
    position_and_account_changes: list = None,
    file_path: str = "",
    transactions_df: pd.DataFrame = None,
    save_curve: bool = True,
) -> pd.DataFrame:
    """
    分析账户变动记录，输出统计结果；可选择是否绘制并保存账户盈利率曲线。

    Args:
        position_and_account_changes: 账户变动记录列表 [{'trade_date', 'stock_count', 'stock_value', 'total_assets'}, ...]
        file_path: 明细 Excel 路径，可选；提供则优先从文件加载数据
        transactions_df: 可选，建仓/清仓分析结果（含建仓时间、涨跌幅），传入则图中增加第三子图
        save_curve: 是否绘制并保存账户盈利率曲线，默认 True

    Returns:
        pd.DataFrame: 单行统计结果 DataFrame
    """
    df = None
    if file_path:
        try:
            df = pd.read_excel(file_path)
        except Exception as e:
            info(f"无法加载文件: {e}")
    elif position_and_account_changes:
        df = pd.DataFrame(position_and_account_changes)
    if df is None or df.empty:
        info("没有有效的账户变动数据")
        return pd.DataFrame()

    if not all(col in df.columns for col in REQ_COLS_ACCOUNT):
        info("缺少关键字段")
        return pd.DataFrame()
    df = df[df['trade_date'].notna()].sort_values("trade_date").reset_index(drop=True)
    if df.empty:
        info("无有效trade_date")
        return pd.DataFrame()

    initial = df.iloc[0]['total_assets']
    final = df.iloc[-1]['total_assets']
    if not initial:
        info("初始资金为0")
        return pd.DataFrame()

    risk_free_rate, trading_days = get_metrics_params()
    rf_daily = risk_free_rate / trading_days  # 日度无风险利率（简单折算）
    ann_factor = np.sqrt(trading_days)        # 年化因子

    profit_rate = final / initial - 1
    roll_max = df['total_assets'].cummax()
    max_drawdown = (df['total_assets'] / roll_max - 1).min()
    max_profit_rate = df['total_assets'].max() / initial - 1  # 账户历史峰值相对初始的涨幅
    max_loss_rate = df['total_assets'].min() / initial - 1    # 账户历史谷值相对初始的跌幅

    # 全区间相邻日收益：用于年化收益、外推提示与基准回归（保持原口径）
    daily_returns = df['total_assets'].pct_change().dropna()
    n = len(daily_returns)              # 有效收益样本天数（按经过的交易日数）

    # 风险类指标（波动率/夏普/索提诺）：按配置口径选取日收益样本。
    # 默认 'active' 剔除纯空仓静止日，避免其 0% 收益稀释标准差、虚高夏普/索提诺。
    risk_basis = get_risk_metric_basis()
    risk_returns, active_days = build_risk_return_series(
        df['total_assets'], df['stock_count'], risk_basis
    )
    risk = compute_return_risk_metrics(risk_returns, rf_daily, ann_factor)
    annual_volatility = risk['annual_volatility']
    sharpe_ratio = risk['sharpe']
    sortino_ratio = risk['sortino']

    # 年化收益率（几何年化，按有效交易日样本）
    annual_return = (final / initial) ** (trading_days / n) - 1 if n > 0 and final > 0 else np.nan
    ar_ok = pd.notnull(annual_return)
    # 卡玛比率：年化收益 / 最大回撤绝对值
    calmar_ratio = annual_return / abs(max_drawdown) if ar_ok and max_drawdown < 0 else np.nan

    # 基准（上证指数）相对指标：超额收益、beta、alpha（CAPM 年化）
    excess_return = beta = alpha = np.nan
    index_profit_rates = _compute_index_profit_rates(df)
    if index_profit_rates is not None and len(index_profit_rates) == len(df) and n > 1:
        idx_value = 1 + np.asarray(index_profit_rates, dtype=float) / 100.0
        bench_daily = pd.Series(idx_value).pct_change().dropna().reset_index(drop=True)
        strat_daily = daily_returns.reset_index(drop=True)
        m = min(len(bench_daily), len(strat_daily))
        bench_daily, strat_daily = bench_daily.iloc[:m], strat_daily.iloc[:m]
        if idx_value[0] > 0 and ar_ok:
            bench_annual = (idx_value[-1] / idx_value[0]) ** (trading_days / n) - 1
            excess_return = annual_return - bench_annual
            var_b = bench_daily.var(ddof=1)
            if var_b and var_b > 0:
                beta = strat_daily.cov(bench_daily) / var_b
                alpha = annual_return - (risk_free_rate + beta * (bench_annual - risk_free_rate))

    max_stock_count = df['stock_count'].max()
    safe_total_assets = df['total_assets'].replace(0, pd.NA)
    max_position_rate = (df['stock_value'] / safe_total_assets).max()
    empty_days = (df['stock_count'] == 0).sum()

    info("=" * 100)
    info("账户分析结果:")
    info(f"初始资金: {initial:,.2f} 元")
    info(f"最终资金: {final:,.2f} 元")
    info(f"盈利率: {profit_rate*100:.2f}%")
    info(f"年化收益率: {fmt_metric(annual_return, pct=True)}")
    info(f"最大回撤: {max_drawdown*100:.2f}%")
    info(f"年化波动率: {fmt_metric(annual_volatility, pct=True)}")
    info(f"夏普比率(年化): {fmt_metric(sharpe_ratio)}")
    info(f"索提诺比率(年化): {fmt_metric(sortino_ratio)}")
    info(f"卡玛比率: {fmt_metric(calmar_ratio)}")
    info(f"超额年化收益(相对上证): {fmt_metric(excess_return, pct=True)}")
    info(f"Beta(相对上证): {fmt_metric(beta)}")
    info(f"Alpha(年化,相对上证): {fmt_metric(alpha, pct=True)}")
    info(f"最大涨幅: {max_profit_rate*100:.2f}%")
    info(f"最大跌幅: {max_loss_rate*100:.2f}%")
    info(f"最大持仓股票数: {max_stock_count}")
    info(f"最大仓位资金占用率: {fmt_metric(max_position_rate, pct=True)}")
    info(f"空仓天数: {empty_days}")
    info(f"有效收益样本天数: {n}")
    info(f"风险指标口径: {risk_basis}（active=剔除纯空仓静止日，避免虚高夏普/索提诺）")
    info(f"风险样本天数: {active_days}")
    annualized_extrapolated = 0 < n < EXTRAPOLATION_MIN_SAMPLE
    if annualized_extrapolated:
        info(f"提示：样本交易日数偏少（n={n}），年化夏普/收益/波动率为外推结果，仅供参考")

    # 绘制账户曲线（复用已算的指数曲线，避免重复查询指数日线）
    if save_curve:
        curve_path = plot_account_profit_curve(
            df, initial, transactions_df=transactions_df, index_profit_rates=index_profit_rates
        )
        if curve_path:
            info(f"账户盈利率曲线已保存: {curve_path}")

    return pd.DataFrame([{
        "init_assets": initial,
        "final_assets": final,
        "profit_rate": profit_rate,
        "annual_return": annual_return,
        "max_drawdown": max_drawdown,
        "annual_volatility": annual_volatility,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "calmar_ratio": calmar_ratio,
        "excess_return": excess_return,
        "beta": beta,
        "alpha": alpha,
        "max_profit_rate": max_profit_rate,
        "max_loss_rate": max_loss_rate,
        "max_stock_count": max_stock_count,
        "max_position_rate": max_position_rate,
        "empty_days": empty_days,
        "sample_days": n,
        "risk_metric_basis": risk_basis,
        "active_days": active_days,
        "annualized_extrapolated": annualized_extrapolated,
    }])

def analyze_buy_and_sell_record(transactions: list = None, file_path: str = "") -> pd.DataFrame:
    """
    分析建仓/清仓记录，支持传文件或交易列表。
    返回结果并存excel：['股票代码','建仓时间','建仓价格','清仓时间','清仓价格','盈亏率','持仓天数']
    支持同一股票多次完整交易，逐次独立分析。
    Args:
        transactions: 交易记录列表
        file_path: 文件路径
        trade_calendar: 交易日历列表
    Returns:
        pd.DataFrame: 分析结果
    """

    if file_path:
        df = pd.read_excel(file_path)
    elif transactions:
        df = pd.DataFrame(transactions)
    else:
        info("没有交易记录")
        return pd.DataFrame()

    start_time = str(df['time'].min())[:8]
    end_time = str(df['time'].max())[:8]
    # 期末仍持仓的交易需按回测截止日估值，交易日历延伸到 config 的回测结束日，保证估值日期落在日历内
    calendar_end = max(end_time, get_backtest_end_time(fallback=end_time))
    trade_calendar = get_trade_calendar(start_time=start_time, end_time=calendar_end)

    df = df.sort_values(["stock_code", "time"])

    # 期末未平仓估值所需的各股票最新收盘价：一次性批量取（替代逐仓查库的 N 次往返）
    last_closes = _get_last_closes(df["stock_code"].unique().tolist(), start_time, calendar_end)

    records = []
    unclosed_marked = 0   # 期末未平仓、已按市值估算并计入的交易数
    unclosed_dropped = 0  # 期末未平仓、因取不到估值价而丢弃的交易数
    for code, g in df.groupby("stock_code"):
        g = g.sort_values("time")
        pos = 0
        n = len(g)
        # 遍历逐笔成交，构建从买入到清仓的交易段（支持多段）
        while pos < n:
            while pos < n and g.iloc[pos]['action'] != 'buy':
                pos += 1
            if pos >= n:
                break
            buy_shares = 0
            buys = []
            # 累计建仓（可跨多笔连续 buy，直到清仓为止）
            while pos < n and g.iloc[pos]['action'] == 'buy':
                buys.append(g.iloc[pos])
                buy_shares += g.iloc[pos]['volume']
                pos += 1
            # 清仓过程
            sells = []
            sell_shares = 0
            while pos < n and g.iloc[pos]['action'] == 'sell' and sell_shares < buy_shares:
                sells.append(g.iloc[pos])
                sell_shares += g.iloc[pos]['volume']
                pos += 1
            # 纯防御：理论上进入循环即有 buy
            if buy_shares == 0:
                continue
            buy_df = pd.DataFrame(buys)
            sell_df = pd.DataFrame(sells)
            # 卖出侧为空时补齐同列空表，保证后续列访问/求和不抛异常
            if sell_df.empty:
                sell_df = pd.DataFrame(columns=buy_df.columns)
            build_t = buy_df.iloc[0]['time']
            # 平均建仓价（按量加权）
            bp = (buy_df['price'] * buy_df['volume']).sum() / buy_shares if buy_shares else 0

            is_closed = sell_shares >= buy_shares
            if is_closed:
                # 已完全清仓：平均清仓价按等量配比
                cp = (sell_df['price'] * sell_df['volume']).sum() / buy_shares if buy_shares else 0
                close_t = sell_df.iloc[-1]['time']
                close_date8 = str(close_t)[:8]
                close_time_disp = time_str_to_datetime(close_t)
            else:
                # 期末未平仓：剩余持仓按回测截止日的收盘价市值估算，不再静默丢弃（避免美化评价）
                remaining = buy_shares - sell_shares
                last_close, last_date8 = last_closes.get(code, (None, None))
                if last_close is None:
                    unclosed_dropped += 1
                    info(f"未平仓交易：{code} 无法取得期末估值价，已丢弃（剩余 {remaining} 股）")
                    continue
                sell_proceeds = (sell_df['price'] * sell_df['volume']).sum()
                # 综合退出价 = (已卖出成交额 + 剩余股数按期末收盘估值) / 建仓总股数
                cp = (sell_proceeds + remaining * last_close) / buy_shares if buy_shares else 0
                close_date8 = last_date8
                close_time_disp = time_str_to_datetime(f"{last_date8}150000") + " (未平仓·期末估值)"
                unclosed_marked += 1

            hold_days = _safe_hold_days(close_date8, str(build_t)[:8], trade_calendar)

            # 毛收益（未扣成本）与净收益（扣双向佣金+卖出印花税）
            # 口径说明：net_rate = 净盈亏 / 买入成交额。分子已扣双向佣金+印花税（total_costs），
            # 分母 buy_cost 取买入成交额（不含买入佣金）；因佣金远小于成交额，二者基数差异对结果影响可忽略。
            buy_cost = bp * buy_shares
            total_commission = buy_df['commission'].sum() + sell_df['commission'].sum()
            total_tax = sell_df['tax'].sum()
            total_costs = total_commission + total_tax
            gross_rate = (cp / bp - 1) if bp > 0 else 0
            net_rate = ((cp * buy_shares - total_costs) / buy_cost - 1) if buy_cost > 0 else 0

            # 合并建仓/卖出信号（拼接多笔desc，去重保留顺序，用 '；' 连接）
            buy_desc = "；".join(
                pd.unique(np.array([str(x).strip() for x in buy_df['desc'] if pd.notna(x) and str(x).strip() != ""]))
            )
            sell_desc = "；".join(
                pd.unique(np.array([str(x).strip() for x in sell_df['desc'] if pd.notna(x) and str(x).strip() != ""]))
            )

            # 交易过程备注：优先使用“分时K线数量”替代时间，记录从建仓到清仓的建仓/卖出全过程及原因
            remarks_parts = []
            has_minute_k = 'minute_k_count' in buy_df.columns and 'minute_k_count' in sell_df.columns

            def _build_prefix(row):
                """生成单笔交易的备注前缀（优先用分时K线数量推算时间，其次回退到原始时间）。"""
                if has_minute_k and pd.notna(row.get("minute_k_count", None)):
                    try:
                        k_count = int(row.get("minute_k_count"))
                    except (TypeError, ValueError):
                        k_count = None
                    if k_count is not None:
                        time_str = minute_k_count_to_time(k_count)
                        return f"{time_str}："
                # 兼容旧数据，退回到时间字符串
                trade_time = time_str_to_datetime(row["time"])
                return f"{trade_time}："

            # 1) 建仓阶段（可能多笔）
            for _, row in buy_df.iterrows():
                desc = str(row.get("desc", "")).strip()
                prefix = _build_prefix(row)
                if desc:
                    remarks_parts.append(f"{prefix}建仓 - {desc}")
                else:
                    remarks_parts.append(f"{prefix}建仓 - 无备注")

            # 2) 卖出阶段（可能多笔）
            for _, row in sell_df.iterrows():
                desc = str(row.get("desc", "")).strip()
                prefix = _build_prefix(row)
                if desc:
                    remarks_parts.append(f"{prefix}卖出 - {desc}")
                else:
                    remarks_parts.append(f"{prefix}卖出 - 无备注")

            sell_remarks = " | ".join(remarks_parts)

            records.append({
                "股票代码": code,
                "建仓时间": time_str_to_datetime(build_t),
                "建仓价格": round(bp, 2),
                "建仓信号": buy_desc,
                "清仓时间": close_time_disp,
                "清仓价格": round(cp, 2),
                "卖出信号": sell_desc,
                "备注": sell_remarks,
                "涨跌幅": round(net_rate, 4),      # 净收益口径（已扣手续费+印花税），胜率/盈亏比据此计算
                "毛涨跌幅": round(gross_rate, 4),   # 毛收益口径（未扣成本），仅供对照
                "是否平仓": is_closed,
                "持仓天数": hold_days,
                "总手续费": total_commission,
                "总印花税": total_tax,
                "总成本": total_costs
            })
            # 卖完后自动进入下一个完整周期（有多段会被while循环依次分析）

    result = pd.DataFrame(
        records,
        columns=[
            "股票代码",
            "建仓时间",
            "建仓价格",
            "清仓时间",
            "清仓价格",
            "涨跌幅",
            "毛涨跌幅",
            "是否平仓",
            "持仓天数",
            "总手续费",
            "总印花税",
            "总成本",
            "备注",
        ],
    )
    fname = f"results/analyze_transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    result.to_excel(fname, index=False)

    if not result.empty:
        # 未平仓估值/丢弃情况，避免"期末留仓被静默剔除"造成评价美化
        if unclosed_marked or unclosed_dropped:
            info(
                f"期末未平仓交易：按期末市值计入 {unclosed_marked} 笔，"
                f"因取不到估值价丢弃 {unclosed_dropped} 笔"
            )
        # 已平仓口径（评价主口径），净收益列（是否平仓 为原生 bool 列，可直接布尔索引）
        closed = result[result["是否平仓"]]
        info("=" * 100)
        for line in format_trade_summary(summarize_trades(closed), title="个股分析结果（已平仓·净收益口径）"):
            info(line)
        # 含未平仓口径（叠加期末市值估算的浮动盈亏），仅在存在未平仓交易时输出
        if unclosed_marked:
            info("-" * 100)
            for line in format_trade_summary(summarize_trades(result), title="个股分析结果（含未平仓·期末市值）"):
                info(line)
    else:
        print("没有交易记录可展示。")
    print(f"交易记录保存文件：{fname}")
    return result