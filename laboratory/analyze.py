"""
分析工具库
"""

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

# 账户变动分析必要列
REQ_COLS_ACCOUNT = ["trade_date", "total_assets", "stock_count", "stock_value"]


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


def plot_account_profit_curve(
    df: pd.DataFrame,
    initial_assets: float,
    save_path: str = None,
    transactions_df: pd.DataFrame = None,
) -> str:
    """
    绘制账户分析图：上为账户累计盈利率曲线，中为持仓比例折线图；若有交易记录则下为按买入日的个股盈利率散点及中位数折线。
    Args:
        df: 含 trade_date、total_assets、stock_value 的账户变动 DataFrame，已按 trade_date 排序
        initial_assets: 初始资金
        save_path: 图片保存路径，为空则自动生成到 results/ 下
        transactions_df: 可选，建仓/清仓分析结果，需含 建仓时间、涨跌幅；传入且非空时绘制第三图
    Returns:
        str: 实际保存的文件路径，未保存则返回空字符串
    """
    if df is None or df.empty or not initial_assets:
        return ""
    days = np.arange(1, len(df) + 1)
    profit_rates = (df["total_assets"].values / initial_assets - 1) * 100
    # 持仓比例 = 持仓价值 / 账户总金额，总金额为 0 时记为 0
    safe_total = np.where(df["total_assets"].values > 0, df["total_assets"].values, np.nan)
    position_ratio = np.where(np.isfinite(safe_total), df["stock_value"].values / safe_total, 0.0)

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

    # 图1：账户累计盈利率曲线，叠加指数盈利率曲线（相对首日）
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

    profit_rate = final / initial - 1
    max_profit_rate = (df['total_assets'].cummax() / initial - 1).max()
    max_loss_rate = (df['total_assets'].cummin() / initial - 1).min()
    roll_max = df['total_assets'].cummax()
    max_drawdown = (df['total_assets'] / roll_max - 1).min()
    # 夏普比率：基于日收益率年化，无风险利率取 0
    daily_returns = df['total_assets'].pct_change().dropna()
    if len(daily_returns) > 0 and daily_returns.std() > 0:
        sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    else:
        sharpe_ratio = np.nan
    max_stock_count = df['stock_count'].max()
    safe_total_assets = df['total_assets'].replace(0, pd.NA)
    max_position_rate = (df['stock_value'] / safe_total_assets).max()
    empty_days = (df['stock_count'] == 0).sum()

    info("=" * 100)
    info("账户分析结果:")
    info(f"初始资金: {initial:,.2f} 元")
    info(f"最终资金: {final:,.2f} 元")
    info(f"盈利率: {profit_rate*100:.2f}%")
    info(f"最大回撤: {max_drawdown*100:.2f}%")
    info(f"夏普比率(年化): {sharpe_ratio:.4f}" if pd.notnull(sharpe_ratio) else "夏普比率(年化): 无法计算")
    info(f"最大涨幅: {max_profit_rate*100:.2f}%")
    info(f"最大跌幅: {max_loss_rate*100:.2f}%")
    info(f"最大持仓股票数: {max_stock_count}")
    info(f"最大仓位资金占用率: {max_position_rate*100:.2f}%" if pd.notnull(max_position_rate) else "最大仓位资金占用率: 无法计算")
    info(f"空仓天数: {empty_days}")

    # 绘制账户曲线（含可选第三图：按买入日个股盈利率散点+中位数折线）
    if save_curve:
        curve_path = plot_account_profit_curve(df, initial, transactions_df=transactions_df)
        if curve_path:
            info(f"账户盈利率曲线已保存: {curve_path}")

    return pd.DataFrame([{
        "init_assets": initial,
        "final_assets": final,
        "profit_rate": profit_rate,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "max_profit_rate": max_profit_rate,
        "max_loss_rate": max_loss_rate,
        "max_stock_count": max_stock_count,
        "max_position_rate": max_position_rate,
        "empty_days": empty_days
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
    trade_calendar = get_trade_calendar(start_time=start_time, end_time=end_time)

    df = df.sort_values(["stock_code", "time"])

    records = []
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
            # 若清仓不完整（买多少没卖完），不计入
            if buy_shares == 0 or sell_shares < buy_shares:
                continue
            # 可合成一次交易
            buy_df = pd.DataFrame(buys)
            sell_df = pd.DataFrame(sells)
            # 按volume配比处理出平均建仓/清仓价
            bp = (buy_df['price'] * buy_df['volume']).sum() / buy_shares if buy_shares else 0
            cp = (sell_df['price'] * sell_df['volume']).sum() / buy_shares if buy_shares else 0  # 卖的是等量
            build_t = buy_df.iloc[0]['time']
            close_t = sell_df.iloc[-1]['time']
            rate = ((cp / bp) - 1) if bp > 0 else 0
            hold_days = get_trade_days_interval(str(close_t)[:8], str(build_t)[:8], trade_calendar)

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

            # 总手续费/印花税
            total_commission = buy_df['commission'].sum() + sell_df['commission'].sum()
            total_tax = sell_df['tax'].sum()
            total_costs = total_commission + total_tax

            records.append({
                "股票代码": code,
                "建仓时间": time_str_to_datetime(build_t),
                "建仓价格": round(bp, 2),
                "建仓信号": buy_desc,
                "清仓时间": time_str_to_datetime(close_t),
                "清仓价格": round(cp, 2),
                "卖出信号": sell_desc,
                "备注": sell_remarks,
                "涨跌幅": round(rate, 4),
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
        info("=" * 100)
        info("个股分析结果:")
        info(f"总交易次数: {len(result)}")
        info(f"胜率: {result[result['涨跌幅'] > 0].shape[0] / len(result) * 100:.2f}%")
        info(f"平均涨跌幅: {result['涨跌幅'].mean()*100:.2f}%")
        info(f"最大涨跌幅: {result['涨跌幅'].max()*100:.2f}%")
        info(f"最小涨跌幅: {result['涨跌幅'].min()*100:.2f}%")
        avg_profit_rate = result[result['涨跌幅'] > 0]['涨跌幅'].mean() * 100
        avg_loss_rate = result[result['涨跌幅'] < 0]['涨跌幅'].mean() * 100
        profit_loss_ratio = avg_profit_rate / avg_loss_rate
        info(f"盈亏和: {result['涨跌幅'].sum()*100:.2f}%")
        info(f"盈亏比：平均涨幅{avg_profit_rate:.2f}%，平均跌幅{avg_loss_rate:.2f}%，盈亏比{-profit_loss_ratio:.2f}") 
        info(f"平均持仓天数: {result['持仓天数'].mean():.2f}")
        # 总交易手续费
        total_commission = result['总手续费'].sum()
        # 总交易印花税
        total_tax = result['总印花税'].sum()
        # 总交易成本
        total_costs = result['总成本'].sum()
        info(f"总交易手续费: {total_commission:,.2f} 元")
        info(f"总交易印花税: {total_tax:,.2f} 元")
        info(f"总交易成本: {total_costs:,.2f} 元")    

        # print("\n个股交易记录:")
        # print(result.to_string(index=False, justify='center', col_space=12))
    else:
        print("没有交易记录可展示。")
    print(f"交易记录保存文件：{fname}")
    return result