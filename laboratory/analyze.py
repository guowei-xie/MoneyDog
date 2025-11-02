"""
分析工具库
"""

import pandas as pd
from datetime import datetime
from utils.util import time_str_to_datetime, get_date_interval, get_trade_days_interval
from utils.logger import info

def analyze_buy_and_sell_record(transactions: list = None, file_path: str = "", trade_calendar: list = None) -> pd.DataFrame:
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
                pd.unique([str(x).strip() for x in buy_df['desc'] if pd.notna(x) and str(x).strip() != ""])
            )
            sell_desc = "；".join(
                pd.unique([str(x).strip() for x in sell_df['desc'] if pd.notna(x) and str(x).strip() != ""])
            )

            records.append({
                "股票代码": code,
                "建仓时间": time_str_to_datetime(build_t),
                "建仓价格": round(bp, 2),
                "建仓信号": buy_desc,
                "清仓时间": time_str_to_datetime(close_t),
                "清仓价格": round(cp, 2),
                "卖出信号": sell_desc,
                "盈亏率": f"{round(rate * 100, 2)}%",
                "持仓天数": hold_days
            })
            # 卖完后自动进入下一个完整周期（有多段会被while循环依次分析）

    result = pd.DataFrame(records, columns=["股票代码", "建仓时间", "建仓价格", "清仓时间", "清仓价格", "盈亏率", "持仓天数"])
    fname = f"results/analyze_transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    result.to_excel(fname, index=False)

    if not result.empty:
        print("\n分析结果:")
        print(result.to_string(index=False, justify='center', col_space=12))
    else:
        print("没有分析结果可展示。")
    print(f"分析结果保存文件：{fname}")
    return result