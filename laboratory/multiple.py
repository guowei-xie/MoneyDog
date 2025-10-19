"""
多K线工具库
"""

from doctest import debug
import pandas as pd
from laboratory.single import is_limit
from utils.logger import info, error


def is_first_board(stock_code: str, daily_bars: pd.DataFrame) -> bool:
    """
    判断是否符合首板图形要求
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
    Returns:
        bool: 是否符合图形要求，True表示符合，False表示不符合
    """
    debug(f"判断是否符合首板图形要求: {stock_code}")

    # 至少需要2条数据
    if len(daily_bars) < 2:
        debug(f"日K线数据不足2条: {stock_code}, 数据: {daily_bars}")
        return False
    
    # 判断当日是否涨停
    if not is_limit(stock_code, daily_bars['close'].iloc[-1], daily_bars['preClose'].iloc[-1]):
        return False
    
    # 判断前一日是否涨停
    if is_limit(stock_code, daily_bars['close'].iloc[-2], daily_bars['preClose'].iloc[-2]):
        return False
    
    return True

def get_last_limit_day(stock_code: str, daily_bars: pd.DataFrame, n: int = 5) -> int:
    """
    获取最近N天内的最后一次涨停日
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
        n: 最近N天内的最后一次涨停日
    Returns:
        int: 最近的涨停日索引, -1表示不存在
    """
    debug(f"获取最近{n}天内的最后一次涨停日: {stock_code}")

    daily_bars_last = daily_bars.iloc[-n:].copy()
    debug(f"截至最近{n}天内的数据: {daily_bars_last}")

    for index, row in daily_bars_last.iterrows():
        if is_limit(stock_code, row['close'], row['preClose']):
            debug(f"获取成功, 索引: {index}")
            return index
    return -1