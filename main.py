"""
MoneyDog 主程序入口
量化交易系统主程序
"""

from utils.logger import info
from strategys.BuyOnDips import BuyOnDips

# 主程序入口
if __name__ == "__main__":
    info("MoneyDog 主程序运行开始")
    strategy = BuyOnDips()
    strategy.run()