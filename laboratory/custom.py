"""
自定义组合图形识别
"""

import pandas as pd
from laboratory.single import is_limit, is_one_board
from laboratory.multiple import get_last_limit_day, is_first_board
from utils.logger import info, error, debug

# 判断是否符合日K线图形：首板后的缩量盘整
def is_first_board_after_volume_consolidation(stock_code: str, daily_bars: pd.DataFrame, n: int = 5, m: int = 10, k: int = 2) -> bool:
    """
    判断是否符合首板后的缩量盘整图形要求
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
        n: 最近{n}个交易日内存在涨停板，且最近一次涨停是首板
        m: 最近{m}个交易日内不能存在一字板首板
        k: 最近{k}个交易日不能是涨停板
    Returns:
        bool: 是否符合图形要求，True表示符合，False表示不符合

    图形要求：
    1. 近{n}个交易日内存在涨停板，且最近一次涨停是首板
    2. 近{m}个交易日内不能存在一字板首板
    3. 最近一次涨停日至少早于当前{k}个交易日
    4. 最近的涨停日次日的成交量不低于涨停日的80%
    5. 最近的涨停日次日至今，成交量逐日递减
    6. 最近的涨停日次日至今，日内震荡幅度处于涨停日价格的-1%~6%之间
    """
    # 判断是否符合条件1
    if not _is_exist_last_first_board(stock_code, daily_bars, n):
        return False
    
    # 判断是否符合条件2
    if _is_exist_one_board(stock_code, daily_bars, m):
        return False
    
    # 判断是否符合条件3
    
    
    # 判断是否符合条件4

    


def _is_exist_last_first_board(stock_code: str, daily_bars: pd.DataFrame, n: int = 5) -> bool:
    """
    判断是否存在最近{n}个交易日内存在涨停板，且最近一次涨停是首板
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
        n: 最近{n}个交易日内存在涨停板，且最近一次涨停是首板
    Returns:
        bool: 是否符合条件，True表示符合，False表示不符合
    """
    debug(f"判断最近{n}个交易日中是否存在涨停板，且最近一次涨停是首板: {stock_code}")
    last_limit_day = get_last_limit_day(stock_code, daily_bars, n)
    if last_limit_day == -1:
        return False

    # 判断最近一次涨停是首板
    # 使用last_limit_day索引, 截断daily_bars后，使用is_first_board判断
    daily_bars_last = daily_bars.loc[last_limit_day:].copy()
    debug(f"截断数据： {daily_bars_last}")
    if not is_first_board(stock_code, daily_bars_last):
        return False
    return True

def _is_exist_one_board(stock_code: str, daily_bars: pd.DataFrame, m: int = 10) -> bool:
    """
    判断是否存在最近{m}个交易日内存在一字板
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
        m: 最近{m}个交易日内存在一字板
    Returns:
        bool: 是否符合条件，True表示符合，False表示不符合
    """
    debug(f"判断是否存在最近{m}个交易日内存在一字板: {stock_code}")
    daily_bars_last = daily_bars.iloc[-m:].copy()
    debug(f"截断数据： {daily_bars_last}")
    for index, row in daily_bars_last.iterrows():
        if is_one_board(stock_code, row['close'], row['preClose'], row['low'], row['high']):
            return True
    return False