"""
工具模块测试模块
"""
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.util import generate_minute_snapshot
from utils.data import get_daily_bars

def test_generate_minute_snapshot():
    """
    测试生成分时行情快照
    """
    stock_list = ['000001.SZ', '000002.SZ']
    daily_bars = get_daily_bars(stock_list, "1m", "20250102", "20250102", count=-1)
    for stock_code, daily_bar in daily_bars.items():
        print(stock_code)
        print(daily_bar)
        print('-'*100)
    snapshots = generate_minute_snapshot(daily_bars)
    for snapshot in snapshots:
        print(snapshot)
        print('-'*100)

test_generate_minute_snapshot()