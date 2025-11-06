"""
分析工具库
"""

import pandas as pd
import numpy as np
from datetime import datetime
from utils.util import time_str_to_datetime, get_date_interval, get_trade_days_interval
from utils.logger import info
from utils.data import get_trade_calendar

def analyze_account_changes(position_and_account_changes: list = None, file_path: str = "") -> pd.DataFrame:
    """
    分析账户变动记录，输出统计结果。
    Args:
        position_and_account_changes: [{'trade_date', 'stock_count', 'stock_value', 'total_assets'}, ...]
        file_path: 明细excel路径, 可选
    Returns:
        pd.DataFrame: 统计结果
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

    # 必要字段检查
    req = ['trade_date','total_assets','stock_count','stock_value']
    if not all(col in df.columns for col in req):
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
    info(f"最大涨幅: {max_profit_rate*100:.2f}%")
    info(f"最大跌幅: {max_loss_rate*100:.2f}%")
    info(f"最大持仓股票数: {max_stock_count}")
    info(f"最大仓位资金占用率: {max_position_rate*100:.2f}%" if pd.notnull(max_position_rate) else "最大仓位资金占用率: 无法计算")
    info(f"空仓天数: {empty_days}")

    return pd.DataFrame([{
        "init_assets": initial,
        "final_assets": final,
        "profit_rate": profit_rate,
        "max_drawdown": max_drawdown,
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
        lots = []
        pos = 0
        n = len(g)
        # 遍历逐笔成交，构建从买入到清仓的交易段（支持多段）
        while pos < n:
            # 找建仓（第一个buy）
            while pos < n and g.iloc[pos]['action'] != 'buy':
                pos += 1
            if pos >= n:
                break
            start_idx = pos
            buy_shares = 0
            buys = []
            # 累计建仓（可跨多笔连续buy，直到清仓为止）
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
                "涨跌幅": round(rate, 4),
                "持仓天数": hold_days,
                "总手续费": total_commission,
                "总印花税": total_tax,
                "总成本": total_costs
            })
            # 卖完后自动进入下一个完整周期（有多段会被while循环依次分析）

    result = pd.DataFrame(records, columns=["股票代码", "建仓时间", "建仓价格", "清仓时间", "清仓价格", "涨跌幅", "持仓天数", "总手续费", "总印花税", "总成本"])
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