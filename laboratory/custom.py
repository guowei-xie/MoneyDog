"""
自定义组合图形识别
"""

import pandas as pd
from laboratory.singleK import is_one_board, is_t_board
from laboratory.multipleK import get_last_limit_day, is_first_board
from utils.logger import debug

def is_exist_last_first_board(stock_code: str, daily_bars: pd.DataFrame, n: int = 5) -> bool:
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
    daily_bars_last = daily_bars.loc[:last_limit_day].copy()
    # debug(f"截断数据： {daily_bars_last}")
    if not is_first_board(stock_code, daily_bars_last):
        return False
    return True

def is_exist_one_board(stock_code: str, daily_bars: pd.DataFrame, m: int = 10) -> bool:
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
    # debug(f"截断数据： {daily_bars_last}")
    for index, row in daily_bars_last.iterrows():
        if is_one_board(stock_code, row['close'], row['preClose'], row['low'], row['high']):
            return True
    return False

def is_exist_t_board(stock_code: str, daily_bars: pd.DataFrame, m: int = 10) -> bool:
    """
    判断是否存在最近{m}个交易日内存在T字板
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
        m: 最近{m}个交易日内存在T字板
    Returns:
        bool: 是否符合条件，True表示符合，False表示不符合
    """
    debug(f"判断是否存在最近{m}个交易日内存在T字板: {stock_code}")
    daily_bars_last = daily_bars.iloc[-m:].copy()
    for index, row in daily_bars_last.iterrows():
        if is_t_board(stock_code, row['close'], row['preClose'], row['open'], row['low'], row['high']):
            return True
    return False