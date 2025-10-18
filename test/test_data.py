import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.data import get_trade_calendar, get_stock_list_in_main_board

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

if __name__ == "__main__":
    # test_get_trade_calendar()
    test_get_stock_list_in_main_board()