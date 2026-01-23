"""
MA5底部确认策略
MA5底部：指的是MA5价格出现反弹的底部区域，反弹日为T，则T-1~T-5的移动平均MA5价格应该是连续下跌的，且T日的MA5价格应该高于T-1日的MA5价格。
MA5顶部：指的是MA5价格出现下跌的顶部区域，下跌日为T，则T-1~T-5的移动平均MA5价格应该是连续上涨的，且T日的MA5价格应该低于T-1日的MA5价格。
而底部确认策略：指的是当出现MA5底部时，该底部价格高于上一次底部价格，则认为该底部是有效的底部，可以买入。
止损线：以上一个（取下方最近的）底部或顶部价格为止损线，当价格跌破止损线时，触发有止损策略。
卖出策略：以MACD指标作为卖出信号，当MACD指标出现红柱缩小时，触发卖出策略。
"""

import pandas as pd
from strategys.BaseStrategy import BaseStrategy
from typing import List, Optional, Dict
from utils.data import get_daily_bars
from laboratory.multipleK import get_ma5_bottom, get_ma_list

class MA5BottomConfirm(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.price_min = 5.0  # 价格区间选股：最低价格
        self.price_max = 60.0  # 价格区间选股：最高价格


    def get_selected_stock_list(self, trade_date: str) -> List[str]:
        """
        获取自选股票列表（预买入）
        Args:
            trade_date: 交易日期
        Returns:
            List[str]: 自选股票列表
        """
        daily_bars = get_daily_bars(stock_list=self.global_stock_list, period="1d", end_time=trade_date, count=90)
        result = []
        for stock_code, daily_bar in daily_bars.items():
            if self._select_stock(stock_code=stock_code, daily_bars=daily_bar):
                result.append(stock_code)
        return result

    def _select_stock(self, stock_code: str, daily_bars: pd.DataFrame) -> bool:
        """
        判断是否符合MA5底部确认条件：
        1. T日收盘价站上MA5价格（T-1日收盘价<MA5价格 & T日收盘价>MA5价格）
        2. T-1日是MA5底部
        3. T-1日的MA5底部高于上一次MA5底部
        Args:
            stock_code: 股票代码
            daily_bars: 日K线数据框
        Returns:
            bool: 是否符合MA5底部确认条件
        """
        # 条件1：T日收盘价站上MA5价格（T-1日收盘价<MA5价格 & T日收盘价>MA5价格）
        ma_list = get_ma_list(daily_bars=daily_bars, period=5)
        if len(ma_list) < 5:
            return False

        is_breakout_ma = daily_bars.iloc[-1]['close'] > ma_list[-1] and daily_bars.iloc[-2]['close'] < ma_list[-2]
        if not is_breakout_ma:
            return False

        # 条件2：T-1日是MA5底部
        ma5_bottom_df = get_ma5_bottom(daily_bars=daily_bars, left_count=5, right_count=1)
        if not ma5_bottom_df.iloc[-2]['is_ma5_bottom']:
            return False

        # 条件3：T-1日的MA5底部高于上一次MA5底部
        # 以左右长度均为5，获取所有MA5底部
        ma5_bottom_df = get_ma5_bottom(daily_bars=daily_bars, left_count=5, right_count=5)
        
        # 获取T-1日的MA5价格（当前底部）
        current_bottom_ma5 = ma5_bottom_df.iloc[-2]['ma5']
        if pd.isna(current_bottom_ma5):
            return False
        
        # 找到T-1日之前的最后一个MA5底部（不包括T-1日本身）
        # 筛选出T-1日之前（iloc[:-2]）所有is_ma5_bottom为True的记录
        data_before_t_minus_1 = ma5_bottom_df.iloc[:-2]
        previous_bottoms = data_before_t_minus_1[data_before_t_minus_1['is_ma5_bottom'] == True]
        
        # 如果之前没有MA5底部，则无法比较，返回False
        if len(previous_bottoms) == 0:
            return False
        
        # 获取最近一次（最后一个）MA5底部的MA5价格
        previous_bottom_ma5 = previous_bottoms.iloc[-1]['ma5']
        if pd.isna(previous_bottom_ma5):
            return False
        
        # 判断：T-1日的MA5底部价格是否高于上一次MA5底部价格
        if current_bottom_ma5 <= previous_bottom_ma5:
            return False

        return True

    def set_cached(self, trade_date: str) -> bool:
        """
        缓存盘前数据（备用于盘中运行）
        Args:
            trade_date: 交易日期
        Returns:
            bool: 是否成功
        """
        # TODO: 后续按策略需要缓存日线/指标等数据
        pass

    def buy_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        买入信号生成
        Args:
            stock_code: 股票代码
            bars: 分时K线快照（DataFrame）
        Returns:
            Optional[Dict]: 买入信号，无信号返回None
        """
        # TODO: 后续实现买入信号逻辑
        pass

    def sell_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        卖出信号生成
        Args:
            stock_code: 股票代码
            bars: 分时K线快照（DataFrame）
        Returns:
            Optional[Dict]: 卖出信号，无信号返回None
        """
        # TODO: 后续实现卖出信号逻辑
        pass

        