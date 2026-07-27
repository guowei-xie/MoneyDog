"""
单K线工具库
"""

from pickle import FALSE
import pandas as pd
from utils.util import get_stock_market_type

def get_limit_percentage(stock_code: str) -> float:
    """
    获取涨跌停幅度（根据股票所属板块）
    Args:
        stock_code: 股票代码
    Returns:
        float: 涨跌停幅度
    """
    market_type = get_stock_market_type(stock_code)

    if market_type == '科创板':
        return 0.20
    elif market_type == '创业板':
        return 0.20
    elif market_type == '北交所':
        return 0.30
    else:
        return 0.10

def is_limit(stock_code: str, price: float, previous_close: float, limit_type: str = 'up', tolerance: float = 0.002) -> bool:
    """
    判断是否涨跌停
    Args:
        stock_code: 股票代码
        price: 当前价格
        previous_close: 前一日收盘价
        limit_type: 涨跌停类型，'up'表示涨停，'down'表示跌停,
        tolerance: 误差范围
    Returns:
        bool: 是否涨跌停
    """
    limit_percentage = get_limit_percentage(stock_code)
    if limit_type == 'up':
        limit_price = previous_close * (1 + limit_percentage - tolerance)
        return price >= limit_price
    elif limit_type == 'down':
        limit_price = previous_close * (1 - limit_percentage + tolerance)
        return price <= limit_price
    else:
        return False


def is_limit_series(stock_code, price, previous_close, limit_type: str = 'up', tolerance: float = 0.002):
    """
    is_limit 的向量化版本：对整列价格/前收盘价一次性判断涨跌停，避免逐行 iterrows。

    与 is_limit 逐元素等价（同一 limit_percentage、同一比较式）。previous_close 为 NaN 时，
    因与 NaN 比较恒为 False，结果自然为 False（与"跳过无前收盘价的行"一致）。

    Args:
        stock_code: 股票代码（决定涨跌停幅度）
        price: 当前价格列（Series 或可转序列）
        previous_close: 前一日收盘价列
        limit_type: 'up' 涨停 / 'down' 跌停
        tolerance: 误差范围
    Returns:
        pd.Series[bool]: 各行是否涨/跌停
    """
    price = pd.Series(price)
    previous_close = pd.Series(previous_close)
    limit_percentage = get_limit_percentage(stock_code)
    if limit_type == 'up':
        return price >= previous_close * (1 + limit_percentage - tolerance)
    elif limit_type == 'down':
        return price <= previous_close * (1 - limit_percentage + tolerance)
    else:
        return pd.Series(False, index=price.index)

# 判断是否一字板
def is_one_board(stock_code: str, price: float, previous_close: float, low: float, high: float, limit_type: str = 'up', tolerance: float = 0.002) -> bool:
    """
    判断是否一字板（判断涨跌停基础上，增加条件：最低价和最高价相等）
    Args:
        stock_code: 股票代码
        price: 当前价格
        previous_close: 前一日收盘价
        limit_type: 涨跌停类型，'up'表示涨停，'down'表示跌停,
        tolerance: 误差范围
    Returns:
        bool: 是否一字涨跌停
    """
    if not is_limit(stock_code, price, previous_close, limit_type, tolerance):
        return False
    if low != high or abs(low - high) > tolerance:
        return False
    return True

# 判断是否T字板
def is_t_board(stock_code: str, price: float, previous_close: float, open: float, low: float, high: float, limit_type: str = 'up', tolerance: float = 0.002) -> bool:
    """
    判断是否T字板
    Args:
        stock_code: 股票代码
        price: 当前价格
        previous_close: 前一日收盘价
        limit_type: 涨跌停类型，'up'表示涨停，'down'表示跌停,
        tolerance: 误差范围
    Returns:
        bool: 是否T字板
    """
    if not is_limit(stock_code, price, previous_close, limit_type, tolerance):
        return False
    if low != high and open == price:
        return True
    return False
        
def get_limit_price(stock_code: str, previous_close: float, limit_type: str = 'up', tolerance: float = 0.002) -> float:
    """
    计算当日涨跌停价
    Args:
        stock_code: 股票代码
        previous_close: 前一日收盘价
        limit_type: 涨跌停类型，'up'表示涨停，'down'表示跌停
        tolerance: 误差范围
    Returns:
        float: 涨跌停价
    """
    limit_percentage = get_limit_percentage(stock_code)
    if limit_type == 'up':
        return round(previous_close * (1 + limit_percentage) - tolerance, 2)
    elif limit_type == 'down':
        return round(previous_close * (1 - limit_percentage) + tolerance, 2)
    else:
        return None

# 计算日内震荡幅度
def get_daily_fluctuation(open: float, low: float, high: float) -> float:
    """
    计算日内震荡幅度
    Args:
        open: 开盘价
        low: 最低价
        high: 最高价
    Returns:
        float: 日内震荡幅度
    """
    return round((high - low) / open, 4)

