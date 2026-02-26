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
from laboratory.multipleK import get_ma5_bottom, get_ma5_top, get_ma_list, get_macd, get_dynamic_daily_kline
from laboratory.singleK import is_limit

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
        daily_bars = self.get_daily_bars_for_selection(trade_date, 90)
        result = []
        for stock_code, daily_bar in daily_bars.items():
            if self._select_stock(stock_code=stock_code, daily_bars=daily_bar):
                result.append(stock_code)
        return result

    def _select_stock(self, stock_code: str, daily_bars: pd.DataFrame) -> bool:
        """
        判断是否符合MA5底部确认条件：
        0. 当前价格在设定的价格区间内（self.price_min <= 收盘价 <= self.price_max）
        1. T日收盘价站上MA5价格（T-1日收盘价<MA5价格 & T日收盘价>MA5价格）
        2. T-1日是MA5底部
        3. T-1日的MA5底部高于上一次MA5底部
        Args:
            stock_code: 股票代码
            daily_bars: 日K线数据框
        Returns:
            bool: 是否符合MA5底部确认条件
        """
        # 条件0：价格在设定区间内（使用最新一日收盘价）
        if daily_bars is None or daily_bars.empty:
            return False
        latest_row = daily_bars.iloc[-1]
        latest_close = float(latest_row['close'])
        if not (self.price_min <= latest_close <= self.price_max):
            return False

        # 条件1补充：T日不能是阴线、不能是涨停
        # 阴线：收盘价 <= 开盘价
        latest_open = float(latest_row['open'])
        if latest_close <= latest_open:
            return False

        # 不能是涨停：使用前一日收盘价判断
        if len(daily_bars) >= 2:
            prev_close = float(daily_bars.iloc[-2]['close'])
            if is_limit(stock_code, latest_close, prev_close, limit_type='up'):
                return False

        # 条件1：T日收盘价站上MA5价格（T-1日收盘价<MA5价格 & T日收盘价>MA5价格）
        ma_list = get_ma_list(daily_bars=daily_bars, period=5)
        if len(ma_list) < 5:
            return False

        is_breakout_ma = daily_bars.iloc[-1]['close'] > ma_list[-1] and daily_bars.iloc[-2]['close'] < ma_list[-2]
        if not is_breakout_ma:
            return False

        # 条件2补充：MA30趋势向上（MA30_T > MA30_T-1）
        ma30_list = get_ma_list(daily_bars=daily_bars, period=30)
        # 至少需要31个交易日数据，才能比较前后两个MA30
        if len(ma30_list) < 31:
            return False
        if pd.isna(ma30_list[-1]) or pd.isna(ma30_list[-2]):
            return False
        if ma30_list[-1] <= ma30_list[-2]:
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
        self.cached = {}
        stock_list = self.selected_stock_list + self.holding_stock_list
        if not stock_list:
            return True

        daily_bars = get_daily_bars(stock_list, "1d", start_time="", end_time=trade_date, count=90)
        for stock_code, daily_bar in daily_bars.items():
            # 缓存日K线数据
            self.cached[stock_code] = {
                'daily_bar': daily_bar
            }
            
            # 如果是持仓股票，计算并缓存止损线
            if stock_code in self.holding_stock_list:
                stop_loss_price = self._calculate_stop_loss_price(stock_code, daily_bar)
                if stop_loss_price is not None:
                    self.cached[stock_code]['stop_loss_price'] = stop_loss_price
        return True

    def buy_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        买入信号生成
        Args:
            stock_code: 股票代码
            bars: 分时K线快照（DataFrame）
        Returns:
            Optional[Dict]: 买入信号，无信号返回None
        """
        # 第1分钟买入（bars数量为1时买入）
        if len(bars) != 1:
            return None
       
        return {
            'action': 'buy',
            'stock_code': stock_code,
            'price': bars.iloc[-1]['close'],
            'volume': self.broker.get_buy_volume(bars.iloc[-1]['close']),
            'minute_k_count': len(bars),
            'time': bars.index[-1], 
            'desc': "第1分钟买入"
        }


    def sell_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        卖出信号生成:
        1. 止盈卖出：MACD指标出现红柱缩小时，触发卖出策略。
        2. 止损卖出：价格跌破止损线时，触发卖出策略。
        Args:
            stock_code: 股票代码
            bars: 分时K线快照（DataFrame）
        Returns:
            Optional[Dict]: 卖出信号，无信号返回None
        """
        # 无持仓不卖出
        available_volume = self.broker.get_available_volume(stock_code)
        if available_volume <= 0:
            return None

        if self._sell_signal_1(stock_code, bars):
            return {
                'action': 'sell',
                'stock_code': stock_code,
                'price': bars.iloc[-1]['close'],
                'volume': available_volume,
                'minute_k_count': len(bars),
                'time': bars.index[-1],
                'desc': "止盈-日线MACD红柱缩短&低于昨收(14:30后)"
            }
        
        signal_2 = self._sell_signal_2(stock_code, bars)
        if signal_2:
            return signal_2
        
        return None

    def _sell_signal_1(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        止盈卖出信号生成：
        1. 14:30后(即分时K线累计数量>=210)，判断是否出现日级别MACD红柱缩小，且当前价低于昨收，如果出现，则卖出。
        2. 昨日MACD必须是大于0的（红柱）。
        Args:
            stock_code: 股票代码
            bars: 分时K线快照（DataFrame）
        Returns:
            bool: 是否触发
        """
        if bars is None or bars.empty:
            return False
        if stock_code not in self.cached or 'daily_bar' not in self.cached[stock_code]:
            return False

        # 1) 时间过滤：14:30之后才判断（等价于分时K线数量>=210）
        if len(bars) < 210:
            return False

        daily_bar = self.cached[stock_code]['daily_bar']
        if daily_bar is None or len(daily_bar) < 2:
            return False

        # 2) 当前价高于昨收：不卖
        yesterday_close = float(daily_bar.iloc[-1]['close'])
        current_price = float(bars.iloc[-1]['close'])
        if current_price > yesterday_close:
            return False

        # 3) 动态拼接“今日”日K，计算日线MACD柱是否缩短
        dynamic_daily_kline = get_dynamic_daily_kline(bars)
        if dynamic_daily_kline is None or dynamic_daily_kline.empty:
            return False

        dynamic_klines = pd.concat([daily_bar, dynamic_daily_kline], ignore_index=True)
        macd_data = get_macd(dynamic_klines)
        if len(macd_data) < 2:
            return False

        today_macd_bar = float(macd_data.iloc[-1]['macd'])
        yesterday_macd_bar = float(macd_data.iloc[-2]['macd'])
        
        # 昨日MACD必须是大于0的（红柱）
        if yesterday_macd_bar <= 0:
            return False
        
        # 今日MACD柱子小于昨日（红柱缩短）
        return today_macd_bar < yesterday_macd_bar

    def _calculate_stop_loss_price(self, stock_code: str, daily_bar: pd.DataFrame) -> Optional[float]:
        """
        计算止损线价格：
        取建仓日前三天的K线，计算最低价作为止损线
        Args:
            stock_code: 股票代码
            daily_bar: 日K线数据框（索引为交易日期，包含'low'列）
        Returns:
            Optional[float]: 止损线价格，如果无法计算则返回None
        """
        # 1. 获取建仓日期
        build_date = self.broker.get_build_date(stock_code)
        if not build_date:
            return None

        # 2. 使用日K线数据的索引来定位建仓日（索引是交易日期）
        df = daily_bar
        if build_date not in df.index:
            return None

        build_idx = df.index.get_loc(build_date)

        # 3. 需要建仓日前至少有3根K线（T-1、T-2、T-3）
        if build_idx < 3:
            return None

        # 4. 取建仓日前三天的K线（不包含建仓日本身），计算最低价作为止损线
        # 区间为 [build_idx-3, build_idx-1]
        window_df = df.iloc[build_idx-3:build_idx]
        if 'low' not in window_df.columns:
            return None

        stop_loss_price = float(window_df['low'].min())
        if pd.isna(stop_loss_price) or stop_loss_price <= 0:
            return None

        return stop_loss_price

    def _sell_signal_2(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        止损卖出信号生成：
        当分时价格低于止损线，则卖出信号生成
        Args:
            stock_code: 股票代码
            bars: 分时K线快照（DataFrame）
        Returns:
            Optional[Dict]: 卖出信号，无信号返回None
        """
        if bars is None or bars.empty:
            return None
        if stock_code not in self.cached:
            return None
        
        # 从缓存中获取止损线价格
        stop_loss_price = self.cached[stock_code].get('stop_loss_price')
        if stop_loss_price is None:
            return None
        
        # 获取建仓价格（用于描述信息）
        build_price = self.broker.get_build_price(stock_code)
        
        # 当分时价格低于止损线，则卖出信号生成
        current_price = float(bars.iloc[-1]['close'])
        if current_price < stop_loss_price:
            available_volume = self.broker.get_available_volume(stock_code)
            if available_volume > 0:
                return {
                    'action': 'sell',
                    'stock_code': stock_code,
                    'price': current_price,
                    'volume': available_volume,
                        'minute_k_count': len(bars),
                    'time': bars.index[-1],
                    'desc': f"止损-价格跌破止损线(止损线:{stop_loss_price:.2f}, 建仓价:{build_price:.2f})"
                }
        
        return None
        