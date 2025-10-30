"""
测试下载历史行情数据
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.data import download_stock_history_data, get_stock_list_in_main_board

def test_download_stock_history_data():
    """
    测试下载历史行情数据
    """
    stock_list = get_stock_list_in_main_board()
    download_stock_history_data(stock_list, start_time="20200101", end_time="20251030", period="1d")
    download_stock_history_data(stock_list, start_time="20200101", end_time="20251030", period="1m")

# 测试下载某日分时K线数据
def test_download_stock_history_data_by_day():
    """
    测试下载某日分时K线数据
    """
    stock_list = ['003007.SZ']
    download_stock_history_data(stock_list, start_time="20240118", end_time="20240118", period="1m")

if __name__ == "__main__":
    # test_download_stock_history_data()
    test_download_stock_history_data_by_day()