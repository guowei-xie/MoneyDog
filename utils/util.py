"""
工具模块
提供基础工具函数，如日期转换、股票代码处理等
"""

import pandas as pd
from utils.logger import error, warning
import time

def date_str_to_num_str(date_str: str) -> str:
    """
    字符串日期转数字日期
    Args:
        date_str: 字符串日期，格式为'YYYY-MM-DD'
    Returns:
        str: 数字日期，格式为'YYYYMMDD'
    """
    return pd.to_datetime(date_str).strftime('%Y%m%d')

def get_num_date_before_n_days(date_str: str, days: int = 1, format: str = 'number') -> str:
    """
    计算某个日期往前推N天的日期，支持数字日期和字符串日期
    Args:
        date_str: 日期，格式为'YYYY-MM-DD' 或 'YYYYMMDD'
        days: 往前推的天数，默认为1
        format: 返回日期格式，'number'或'str'
            'number': 返回日期为数字格式，如'20240101'
            'str': 返回日期为字符串格式，如'2024-01-01'
    Returns:
        str: 往前推N天的日期，格式为'number'或'str'
    """
    date = pd.to_datetime(date_str)
    date = date - pd.Timedelta(days=days)
    if format == 'number':
        return date.strftime('%Y%m%d')
    elif format == 'str':
        return date.strftime('%Y-%m-%d')
    else:
        error(f"无效的格式: {format}")
        raise ValueError(f"无效的格式: {format}")

def add_stock_suffix(stock_code):
    """
    为给定的股票代码添加相应的后缀
    Args:
        stock_code: 股票代码，可以带后缀如.SH/.SZ，也可以不带
    Returns:
        str: 添加后缀的股票代码，如'000001.SH'
    """
    # 如果已经有后缀，直接返回
    if '.' in stock_code:
        return stock_code
        
    # 检查股票代码是否为6位数字
    if len(stock_code) != 6 or not stock_code.isdigit():
        raise ValueError("股票代码必须是6位数字")

    # 根据股票代码的前缀添加相应的后缀
    if stock_code.startswith(("00", "30", "15", "16", "18", "12")):
        return f"{stock_code}.SZ"  # 深圳证券交易所
    elif stock_code.startswith(("60", "68", "11")):
        return f"{stock_code}.SH"  # 上海证券交易所
    elif stock_code.startswith(("83", "43")):
        return f"{stock_code}.BJ"  # 北京证券交易所
    
    return f"{stock_code}.SH"  # 默认为上海证券交易所

def add_stock_suffix_list(stock_list: list) -> list:
    """
    为给定的股票代码列表添加相应的后缀
    Args:
        stock_list: 股票代码列表
    Returns:
        list: 添加后缀的股票代码列表
    """
    return [add_stock_suffix(stock_code) for stock_code in stock_list]

def get_stock_market_type(stock_code: str) -> str:
    """
    根据股票代码判断股票所属市场类型
    Args:
        stock_code: 股票代码，可以带后缀如.SH/.SZ，也可以不带
    Returns:
        str: 市场类型，'主板'/'创业板'/'科创板'/'北交所'
    """
    symbol = add_stock_suffix(stock_code)
    if '.' in symbol:
        symbol = symbol.split('.')[0]
    if symbol.startswith('688') or symbol.startswith('689'):
        return '科创板'
    elif symbol.startswith('30'):
        return '创业板'
    elif symbol.startswith('83'):
        return '北交所'
    else:
        return '主板'

def generate_minute_snapshot(daily_bars: dict) -> list:
    """
    生成分时行情快照
    Args:
        daily_bars: 股票池各股票的分时K线数据，形式如{"000001.SZ": DataFrame, ...}
    Returns:
        list: 分时快照数据 [{'minute': minute, 'snapshot': [{'stock_code': stock_code, 'bars': bars}]}]
    """
    # 1. 所有股票的所有index（分钟时间戳）集合
    all_minute_set = set()
    for df in daily_bars.values():
        if len(df) > 0:
            # 支持index为datetime或str
            idx = df.index.astype(str)
            all_minute_set |= set(idx)
        else:
            warning(f"股票{stock_code}的分时K线数据为空")
    if not all_minute_set:
        return []

    # 2. 对齐时间: 升序
    all_minutes = sorted(all_minute_set)
    snapshots = []
    for minute in all_minutes:
        snap = []
        for stock_code, df in daily_bars.items():
            if len(df) == 0:
                continue
            # df.index可能是DatetimeIndex或str, 为保证兼容统一转str比较
            str_index = df.index.astype(str)
            # 选取所有小于等于当前minute的bars
            # 假定数据已是当日/已按时间排序
            if minute in str_index.values:
                # 取出从开盘至当前minute的所有bars
                bars = df.loc[str_index <= minute].copy()
                # 如果bars非空
                if len(bars) > 0:
                    snap.append({'stock_code': stock_code, 'bars': bars})
        snapshots.append({'minute': minute, 'snapshot': snap})
    return snapshots


def get_date_interval(date1: str, date2: str) -> int:
    """
    计算两个数字格式日期的间隔天数
    Args:
        date1: 日期1，格式为'YYYYMMDD'
        date2: 日期2，格式为'YYYYMMDD'
    Returns:
        int: 间隔天数
    """
    return (pd.to_datetime(date1) - pd.to_datetime(date2)).days

def get_elapsed_time_str(start_time: float) -> str:
    """
    计时器，返回耗时小时:分钟:秒字符串
    Args:
        start_time: 开始时间 float，如time.time()
    Returns:
        str: 耗时小时:分钟:秒字符串，如'01小时:02分:03秒'
    """
    elapsed = time.time() - start_time
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = int(elapsed % 60)
    return f"{hours}小时{minutes}分{seconds}秒"

# 时间转换，例如 20250909093900 转换为 2025-09-09 09:39:00
def time_str_to_datetime(time_str: str) -> str:
    """
    时间转换，例如 20250909093900 转换为 2025-09-09 09:39:00
    Args:
        time_str: 时间字符串，格式为'YYYYMMDDHHMMSS'
    Returns:
        str: 时间字符串，格式为'YYYY-MM-DD HH:MM:SS'，例如 '2025-09-09 09:39:00'
    """
    return pd.to_datetime(time_str, format='%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')

#  数字日期加减天数，返回数字日期，例如 20250909 加1天，返回 20250910，减1天，返回 20250908
def add_num_date_days(date_str: str, days: int) -> str:
    """
    数字日期加减天数，返回数字日期
    Args:
        date_str: 日期字符串，格式为'YYYYMMDD'
        days: 天数
    Returns:
        str: 日期字符串，格式为'YYYYMMDD'
    """
    # 检查date_str格式和长度，确保为8位数字
    if not (isinstance(date_str, str) and len(date_str) == 8 and date_str.isdigit()):
        raise ValueError(f"date_str必须为8位数字字符串，实际为: {date_str}")
    new_date = pd.to_datetime(date_str, format='%Y%m%d') + pd.Timedelta(days=days)
    return new_date.strftime('%Y%m%d')