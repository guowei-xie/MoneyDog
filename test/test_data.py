import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.data import *
def test_get_trade_calendar():
    """
    测试获取交易日历
    """
    start_time = "20250101"
    end_time = "20250131"
    trade_calendar = get_trade_calendar(start_time, end_time, format='number')
    print(trade_calendar)
    
    start_time = "2025-01-01"
    end_time = "2025-01-31"
    trade_calendar = get_trade_calendar(start_time, end_time, format='str')
    print(trade_calendar)

def test_get_stock_list_in_main_board():
    """
    测试获取沪深A股主板成分股
    """
    stock_list = get_stock_list_in_main_board()
    print(stock_list)

def test_get_daily_bars():
    """
    测试获取K线数据
    """
    # stock_list = ['000001.SZ', '000002.SZ']
    # # 测试获取日K线数据
    # daily_bars = get_daily_bars(stock_list, "1d", "20250101", "", count=-1)
    # for stock_code, daily_bar in daily_bars.items():
    #     print(stock_code)
    #     print(daily_bar)
    #     print('-'*100)

    # # 测试获取分时K线数据
    # stock_list = ['603102.SH', '603615.SH']
    # daily_bars = get_daily_bars(stock_list, "1m", "20250101", "", count=-1)
    # for stock_code, daily_bar in daily_bars.items():
    #     print(stock_code)
    #     print(daily_bar)
    #     print('-'*100)

    # 测试某日分时K线数据
    daily_bars = get_daily_bars(stock_list=['003007.SZ'], period='1m', start_time='20240118', end_time='20250118', count=-1)
    daily_bars = daily_bars['003007.SZ']
    print(daily_bars)

if __name__ == "__main__":
    # test_get_trade_calendar()
    # test_get_stock_list_in_main_board()
    test_get_daily_bars()