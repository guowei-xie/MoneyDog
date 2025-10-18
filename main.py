"""
MoneyDog 主程序入口
量化交易系统主程序
"""

from utils.logger import debug, info
from utils.data import get_trade_calendar
from strategys.BuyOnDips import BuyOnDips
import configparser

# 主程序入口
if __name__ == "__main__":
    info("MoneyDog 主程序运行开始")
    strategy = BuyOnDips(backtest_start_time="20250101", backtest_end_time="20250131", download_start_time="20250101")
    strategy.prepare()

    # trade_calendar = get_trade_calendar(strategy.backtest_start_time, strategy.backtest_end_time)

   
