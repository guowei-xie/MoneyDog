"""
数据工具模块
提供数据处理和获取功能
"""

import pandas as pd
import akshare as ak
from xtquant import xtdata
from utils.logger import debug, error
from utils.util import get_stock_market_type, add_stock_suffix_list
from tqdm import tqdm

# 获取交易日历
def get_trade_calendar(start_time: str, end_time: str, format: str = 'number') -> list:
    """
    获取交易日历
    Args:
        start_time: 开始时间，格式为'number'或'str'
        end_time: 结束时间，格式为'number'或'str'
        format: 格式，'number'或'str'
            'number': 返回日期为数字格式，如20240101
            'str': 返回日期为字符串格式，如'2024-01-01'
    Returns:
        list: 交易日历，格式为'number'或'str'
    """
    start = pd.to_datetime(start_time)
    end = pd.to_datetime(end_time)
    
    try:
        dates = ak.tool_trade_date_hist_sina()['trade_date']
    except Exception as e:
        error(f"调用akshare交易日历接口失败: {e}")
        raise RuntimeError(f"调用akshare交易日历接口失败: {e}")

    dates = pd.to_datetime(dates)
    mask = (dates >= start) & (dates <= end)

    if format == 'number':
        return [dt.strftime('%Y%m%d') for dt in dates[mask]]
    elif format == 'str':
        return [dt.strftime('%Y-%m-%d') for dt in dates[mask]]
    else:
        error(f"无效的格式: {format}")
        raise ValueError(f"无效的格式: {format}")

# 获取板块成分股
def get_stock_list_in_sector(sector_name: str) -> list:
    """
    获取板块成分股
    Args:
        sector_name: 板块名称(如: '沪深A股')
    Returns:
        list: 板块成分股代码列表
    """
    try:
        stock_list = xtdata.get_stock_list_in_sector(sector_name)
        return stock_list
    except Exception as e:
        error(f"获取板块成分股失败: {e}")
        raise RuntimeError(f"获取板块成分股失败: {e}")

def get_stock_list_in_main_board() -> list:
    """
    获取沪深A股主板成分股
    Returns:
        list: 沪深A股主板成分股代码列表
    """
    try:
        sector_name = '沪深A股'
        stock_list = get_stock_list_in_sector(sector_name)
        stock_list = [stock for stock in stock_list if get_stock_market_type(stock) == '主板']
        return stock_list
    except Exception as e:
        error(f"获取{sector_name}主板成分股失败: {e}")
        raise RuntimeError(f"获取{sector_name}主板成分股失败: {e}")

# 下载股票历史数据
def download_stock_history_data(stock_list: list, start_time: str, end_time: str = '', period: str = '1d', process_bar: bool = True) -> bool:
    """
    下载股票历史K线数据
    Args:
        stock_list: 股票代码列表
        start_time: 开始时间
        period: 周期
            '1d': 日线(默认)
            '1m': 1分钟线
        process_bar: 进度条显示，默认显示
    Returns:
        bool: 是否成功
    """
    if not stock_list:
        error(f"股票列表为空")
        raise ValueError(f"股票列表为空")

    if not start_time:
        error(f"开始时间不能为空")
        raise ValueError(f"开始时间不能为空")
    
    if not period:
        error(f"周期不能为空")
        raise ValueError(f"周期不能为空")
    
    iterator = tqdm(stock_list, desc=f"下载历史数据", ncols=100, colour="green") if process_bar else stock_list
    for code in iterator:
        xtdata.download_history_data(code, period=period, start_time=start_time, end_time=end_time, incrementally=True)
    return True

# 获取行情数据
def get_daily_bars(stock_list: list, period: str = '1d', start_time: str = '', end_time: str = '', count: int = -1) -> dict:
    """
    获取行情数据
    Args:
        stock_list: 股票列表
        period: 周期
        start_time: 开始时间
        end_time: 结束时间
        count: 数量
    Returns:
        dict: 行情数据
    """
    try:
        dict_data = xtdata.get_market_data_ex(
            field_list=[],
            stock_list=add_stock_suffix_list(stock_list),
            period=period,
            start_time=start_time,
            end_time=end_time,
            count=count,
            dividend_type='none',
            fill_data=True
        )
        return dict_data
    except Exception as e:
        error(f"获取行情数据失败: {e}")
        raise RuntimeError(f"获取行情数据失败: {e}")
