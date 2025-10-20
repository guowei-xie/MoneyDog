"""
单K线工具库
"""

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


