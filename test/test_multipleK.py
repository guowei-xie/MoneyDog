"""
多K线工具库测试模块
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from laboratory.multipleK import is_first_board, get_last_limit_day, get_daily_bars_by_date, get_ma, get_macd, get_volume_change_rate, get_average_volume
from utils.data import get_daily_bars

def test_is_first_board():
    """
    测试is_first_board函数
    """
    # 测试数据集20251010为首板
    # 1. 测试非首板（当日未涨停）
    daily_bars = get_daily_bars(stock_list=['002291.SZ'], period='1d', end_time='20251020', count=30)
    daily_bars = daily_bars['002291.SZ']
    print(daily_bars)
    is_first_board_result = is_first_board(stock_code='002291.SZ', daily_bars=daily_bars)
    print(is_first_board_result)

    # 2. 测试首板
    daily_bars = get_daily_bars(stock_list=['002291.SZ'], period='1d', end_time='20251010', count=30)
    daily_bars = daily_bars['002291.SZ']
    print(daily_bars)
    is_first_board_result = is_first_board(stock_code='002291.SZ', daily_bars=daily_bars)
    print(is_first_board_result)

    # 测试数据集20251019~20251020为连板
    # 3. 测试非首板（当日涨停，但前1日未涨停）
    daily_bars = get_daily_bars(stock_list=['600408.SH'], period='1d', end_time='20251020', count=30)
    daily_bars = daily_bars['600408.SH']
    print(daily_bars)
    is_first_board_result = is_first_board(stock_code='600408.SH', daily_bars=daily_bars)
    print(is_first_board_result)

def test_get_last_limit_day():
    """
    测试get_last_limit_day函数
    """
     # 测试数据集20251010为首板
    daily_bars = get_daily_bars(stock_list=['002291.SZ'], period='1d', end_time='20251020', count=30)
    daily_bars = daily_bars['002291.SZ']
    print(daily_bars)
    last_limit_day = get_last_limit_day(stock_code='002291.SZ', daily_bars=daily_bars, n=10)
    print(last_limit_day)

    # 测试：限制天数内不存在涨停板
    last_limit_day = get_last_limit_day(stock_code='002291.SZ', daily_bars=daily_bars, n=5)
    print(last_limit_day)

    # 测试数据集20251019~20251020为连板
    daily_bars = get_daily_bars(stock_list=['600408.SH'], period='1d', end_time='20251020', count=30)
    daily_bars = daily_bars['600408.SH']
    print(daily_bars)
    last_limit_day = get_last_limit_day(stock_code='600408.SH', daily_bars=daily_bars, n=5)
    print(last_limit_day)

def test_get_daily_bars_by_date():
    """
    测试get_daily_bars_by_date函数
    """
    # 测试数据集20251010为首板
    daily_bars = get_daily_bars(stock_list=['002291.SZ'], period='1d', end_time='20251015', count=30)
    daily_bars = daily_bars['002291.SZ']
    print(daily_bars)
    last_limit_day = get_last_limit_day(stock_code='002291.SZ', daily_bars=daily_bars, n=5)
    after_last_limit_day_bars = get_daily_bars_by_date(daily_bars, start_date=last_limit_day, end_date=daily_bars.index[-1])
    print(after_last_limit_day_bars)

def test_get_ma():
    """
    test_get_ma函数
    """
    daily_bars = get_daily_bars(stock_list=['002291.SZ'], period='1d', end_time='20251020', count=30)
    daily_bars = daily_bars['002291.SZ']
    print(daily_bars)
    ma_price = get_ma(daily_bars=daily_bars, period=30)
    print(ma_price)

def test_get_macd():
    """
    test_get_macd函数
    """
    daily_bars = get_daily_bars(stock_list=['002291.SZ'], period='1d', end_time='20251020', count=30)
    daily_bars = daily_bars['002291.SZ']
    macd_data = get_macd(daily_bars=daily_bars)
    print(macd_data)

def test_get_average_volume():
    """
    test_get_average_volume函数
    """
    daily_bars = get_daily_bars(stock_list=['002291.SZ'], period='1d', end_time='20251020', count=30)
    daily_bars = daily_bars['002291.SZ']
    daily_bars = get_average_volume(daily_bars=daily_bars)
    print(daily_bars)

def test_get_volume_change_rate():
    """
    test_get_volume_change_rate函数
    """
    daily_bars = get_daily_bars(stock_list=['002291.SZ'], period='1d', end_time='20251020', count=30)
    daily_bars = daily_bars['002291.SZ']
    volume_change_rate = get_volume_change_rate(daily_bars=daily_bars)
    print(volume_change_rate)

if __name__ == '__main__':
    # test_is_first_board()
    # test_get_last_limit_day()
    # test_get_daily_bars_by_date()
    # test_get_ma()
    test_get_macd()
    # test_get_volume_change_rate()
    # test_get_average_volume()