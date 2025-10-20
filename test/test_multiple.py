"""
多K线工具库测试模块
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from laboratory.multiple import is_first_board, get_last_limit_day
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

if __name__ == '__main__':
    # test_is_first_board()
    test_get_last_limit_day()