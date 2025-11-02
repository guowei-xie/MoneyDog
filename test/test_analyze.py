"""
分析工具测试模块
"""

import os
import sys
# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.data import get_trade_calendar
from laboratory.analyze import analyze_buy_and_sell_record, analyze_account_changes


def test_analyze_buy_and_sell_record():
    """
    测试分析建仓、清仓记录
    """
    file_path = "results/original_transactions_20251102_182354.xlsx"
    trade_calendar = get_trade_calendar("20241030", "20251030")
    analyze_buy_and_sell_record(file_path=file_path, trade_calendar=trade_calendar)
if __name__ == "__main__":
    test_analyze_buy_and_sell_record()