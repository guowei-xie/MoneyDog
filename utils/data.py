"""
数据工具模块
提供数据处理和获取功能
"""

import pandas as pd
import akshare as ak
# from xtquant import xtdata
from utils.logger import debug, error
from utils.util import get_stock_market_type, add_stock_suffix_list
from tqdm import tqdm
from utils.duckdb import DuckDBHelper
from utils.util import date_to_timestamp, timestamp_to_date, timestamp_to_time
duckdb_helper = DuckDBHelper()

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
        sql = f"SELECT code FROM stock_list"
        df = duckdb_helper.conn.execute(sql).df()
        return df['code'].values.tolist()
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

# 获取行情数据
def get_daily_bars(
    stock_list: list, 
    period: str = '1d', 
    start_time: str = '', 
    end_time: str = '', 
    count: int = -1, 
    add_preclose: bool = True,
    table_name: str = ''
) -> dict:
    """
    获取行情数据
    Args:
        stock_list: 股票列表
        period: 周期 '1d' 或 '1m'
        start_time: 开始时间（如 '20240101'）
        end_time: 结束时间
        count: 数量。如果为-1，则返回所有；如果>0，优先生效count条（从最新时间往前取）
        add_preclose: 是否添加前收盘价。如果为True，则添加前收盘价
        table_name: 表名(如: 'daily_1day' 或 'daily_1min' 或 'index_daily')
    Returns:
        dict: {stock_code: DataFrame}
    """
    if not stock_list:
        error("股票列表为空")
        raise ValueError("股票列表为空")

    if table_name == '':
        if period == '1d':
            table_name = 'daily_1day'
        elif period == '1m':
            table_name = 'daily_1min'
        else:
            error(f"不支持的周期: {period}")
            raise ValueError(f"不支持的周期: {period}")

    start_ts = date_to_timestamp(start_time) if start_time else None
    end_ts = date_to_timestamp(end_time, at_end_of_day=True) if end_time else None

    # 仅选取常用字段（可按需扩展）
    fields = "code, time, open, high, low, close, volume, amount"
    # 构造批量查询SQL
    code_list_str = ','.join([f"'{code}'" for code in stock_list])
    where_clause = [f"code IN ({code_list_str})"]
    if start_ts is not None:
        where_clause.append(f"time >= {start_ts}")
    if end_ts is not None:
        where_clause.append(f"time <= {end_ts}")
    where_sql = " AND ".join(where_clause)
    sql = f"SELECT {fields} FROM {table_name} WHERE {where_sql} ORDER BY code, time"
    df_all = duckdb_helper.conn.execute(sql).df()

    # 批量处理所有股票数据，避免Python循环，使用向量化操作提升性能
    # 1. 添加前收盘价（如果需要）- 使用groupby向量化操作
    if add_preclose:
        df_all['preClose'] = df_all.groupby('code', sort=False)['close'].shift(1)
    
    # 2. 如果count>0，每只股票从最新向前截取count条 - 使用groupby向量化操作
    if count > 0:
        df_all = df_all.groupby('code', sort=False).tail(count).reset_index(drop=True)
    
    # 3. 批量设置index - 在整个DataFrame上一次性完成，避免循环
    if period == '1d':
        # 向量化转换：将时间戳Series转换为datetime后格式化
        df_all['index'] = pd.to_datetime(df_all['time'], unit='ms', utc=True)\
                     .dt.tz_convert('Asia/Shanghai')\
                     .dt.strftime('%Y%m%d')
    elif period == '1m':
        # 向量化转换：将时间戳Series转换为datetime后格式化
        df_all['index'] = pd.to_datetime(df_all['time'], unit='ms', utc=True)\
                     .dt.strftime('%Y%m%d%H%M%S')
    else:
        error(f"不支持的周期: {period}")
        raise ValueError(f"不支持的周期: {period}")
    
    # 4. 设置index并转换为字典格式
    # 注意：groupby操作在底层是C级别优化的，比Python循环快得多
    df_all = df_all.set_index('index')
    # 使用groupby分组，并在每个分组中移除code列（因为code已作为字典的key）
    daily_bars = {code: group_df.drop(columns=['code']) 
                  for code, group_df in df_all.groupby('code', sort=False)}
    
    return daily_bars
