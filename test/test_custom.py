"""
自定义图形识别测试模块
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategys.BaseStrategy import BaseStrategy

from laboratory.custom import dual_momentum_breakout
from utils.data import get_daily_bars, get_stock_list_in_main_board

def test_dual_momentum_breakout():
    """
    test_dual_momentum_breakout函数
    """
    stock_list = get_stock_list_in_main_board()
    daily_bars = get_daily_bars(stock_list=stock_list, period='1d', end_time='20251125', count=30)
    for stock_code, daily_bar in daily_bars.items():
        is_dual_momentum_breakout = dual_momentum_breakout(stock_code=stock_code, daily_bars=daily_bar)
        if is_dual_momentum_breakout:
            print(f"{stock_code}: {is_dual_momentum_breakout}")
    


if __name__ == "__main__":
    test_dual_momentum_breakout()
    
   