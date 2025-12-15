"""
双重动量突破策略
"""
from strategys.BaseStrategy import BaseStrategy
from utils.data import get_daily_bars
from typing import List, Optional, Dict
import pandas as pd
from laboratory.custom import dual_momentum_breakout
from laboratory.multipleK import get_ma, get_macd, is_macd_top
from laboratory.singleK import is_limit, get_limit_price
from utils.util import convert_to_safe_sell_volume

class DualMomentumBreakout(BaseStrategy):
    """
    双均线突破策略
    """
    def __init__(self):
        super().__init__()
        self.price_min = 5.0  # 价格区间选股：最低价格
        self.price_max = 60.0  # 价格区间选股：最高价格
        self.batch_sell_count = 2 # 卖出时分批次数

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
            if dual_momentum_breakout(stock_code=stock_code, daily_bars=daily_bar):
                result.append(stock_code)
        return result

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
        daily_bars = get_daily_bars(stock_list, "1d", start_time="", end_time=trade_date, count=30)
        for stock_code, daily_bar in daily_bars.items():
            # 初始化字典，防止KeyError
            self.cached[stock_code] = {}
            # 缓存行情数据
            self.cached[stock_code]['daily_bar'] = daily_bar
            # 缓存MACD数据
            self.cached[stock_code]['macd_data'] = get_macd(daily_bar)
            # 剩余卖出分批次数
            self.cached[stock_code]['batch_sell_count'] = self.batch_sell_count
        return True
        
    def on_minute_end(self, stock_code: str, bars: pd.DataFrame):
        """
        策略盘中分时线运行结束后运行
        1. 更新顶部顶点价格
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        """
        # 更新顶部顶点价格
        if stock_code in self.cached:
            macd_data = get_macd(bars)
            if is_macd_top(macd_data):
                self.cached[stock_code]['top_price'] = bars.iloc[-1]['close']
        return True
        
    def buy_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        买入信号生成
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        
        1. 开盘价格不低于动态MA5价格
        2. 分时价格等于动态MA5价格

        Returns:
            Optional[Dict]: 买入信号 {'action': 'buy', 'stock_code': stock_code, 'price': price, 'volume': volume, 'time': time, 'desc': desc}，无信号返回None
        """
        # 判断是否已持仓
        if stock_code in self.broker.positions:
            return None
       
        signal_1 = self._buy_signal_1(stock_code, bars)
        if not signal_1:
            return None
        signal_2 = self._buy_signal_2(stock_code, bars)
        if not signal_2:
            return None
        return {
            'action': 'buy',
            'stock_code': stock_code,
            'price': bars.iloc[-1]['close'],
            'volume': self.broker.get_buy_volume(bars.iloc[-1]['close']),
            'time': bars.index[-1],
            'desc': ""
        }

    def _buy_signal_1(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        买入信号1:
        1. 开盘价格不低于动态MA5价格
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        klines = self.cached[stock_code]['daily_bar']
        # 动态MA5 = (MA4 * 4 + 当前价) / 5
        ma4 = get_ma(klines, period=4)
        dynamic_ma5 = (ma4 * 4 + klines.iloc[-1]['close']) / 5
        # 开盘价格不低于动态MA5价格
        if bars.iloc[0]['open'] <= dynamic_ma5:
            return False
        return True
        
    def _buy_signal_2(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        买入信号2:
        1. 分时价格等于动态MA5价格
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        klines = self.cached[stock_code]['daily_bar']
        # 动态MA5 = (MA4 * 4 + 当前价) / 5
        ma4 = get_ma(klines, period=4)
        dynamic_ma5 = (ma4 * 4 + klines.iloc[-1]['close']) / 5
        # 分时价格等于动态MA5价格
        if bars.iloc[-1]['close'] >= dynamic_ma5:
            return False
        return True

    def sell_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        卖出信号生成
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        
        1. 昨日日线MACD为负向且当前动态MACD亦为负向
        2. 昨日放量10%以上阳线
        3. 昨日涨停或跌停或上板失败
        4. 今日上板失败
        5. 当日分时MACD顶点（可选条件：是否低于上一个顶部顶点价格）
        6. 炸板
        7. 跌停

        Returns:
            Optional[Dict]: 卖出信号 {'action': 'sell', 'stock_code': stock_code, 'price': price, 'volume': volume, 'time': time, 'desc': desc}，无信号返回None
        """
         # 屏蔽信号：当前涨停，不卖出
        if self._sell_shield_signal(stock_code, bars):
            return None

        # 获取可用卖出数量
        available_volume = self.broker.get_available_volume(stock_code)
        if available_volume <= 0:
            return None

        # 卖出信号
        signal_1 = self._sell_signal_1(stock_code, bars)
        signal_2 = self._sell_signal_2(stock_code, bars)
        signal_3 = self._sell_signal_3(stock_code, bars)
        signal_4 = self._sell_signal_4(stock_code, bars)
        signal_5 = self._sell_signal_5(stock_code, bars, compare_top_price=True)
        signal_5_2 = self._sell_signal_5(stock_code, bars)
        signal_6 = self._sell_signal_6(stock_code, bars)
        signal_7 = self._sell_signal_7(stock_code, bars)
        
        # 组合1：（1 or 2 or 3 or 7） and 5 分批卖出
        if (signal_1 or signal_2 or signal_3 or signal_7) and signal_5:
             # 获取剩余卖出分批次数
            batch_sell_count = self.cached[stock_code]['batch_sell_count']
            # 计划卖出数量 = 可用卖出数量 / 剩余卖出分批次数
            plan_sell_volume = available_volume / batch_sell_count
            # 转化为安全的卖出数量
            sell_volume = convert_to_safe_sell_volume(plan_sell_volume, available_volume)

            if sell_volume > 0:
                # 更新剩余卖出分批次数
                self.cached[stock_code]['batch_sell_count'] -= 1
                return {
                    'action': 'sell',
                    'stock_code': stock_code,
                    'price': bars.iloc[-1]['close'],
                    'volume': sell_volume,
                    'time': bars.index[-1],
                    'desc': f"组合1: （{int(signal_1)} | {int(signal_2)} | {int(signal_3)}） & {int(signal_5)}"
                }

        # 组合2： (4 or 6) and 5_2; 清仓卖出
        if (signal_4 or signal_6) and signal_5_2:
            return {
                'action': 'sell',
                'stock_code': stock_code,
                'price': bars.iloc[-1]['close'],
                'volume': available_volume,
                'time': bars.index[-1],
                'desc': f"组合2: （{int(signal_4)} | {int(signal_5)}） & {int(signal_5_2)}"
            }



    def _sell_signal_1(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号1:
        1. 昨日日线MACD为负趋势且当前动态MACD亦为负趋势
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        klines = self.cached[stock_code]['daily_bar']
        macd_data = self.cached[stock_code]['macd_data']
        # 昨日日线MACD为负趋势
        is_macd_down_yesterday = macd_data.iloc[-1]['macd'] < macd_data.iloc[-2]['macd']
        # 当日日线MACD亦为负趋势(将当前分时bar添加到klines中，计算macd)
        klines_today = pd.concat([klines, bars.iloc[-1:]], ignore_index=True)
        macd_data_today = get_macd(klines_today)
        is_macd_down_today = macd_data_today.iloc[-1]['macd'] < macd_data_today.iloc[-2]['macd']
        if is_macd_down_yesterday and is_macd_down_today:
            return True
        return False

    def _sell_signal_2(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号2:
        1. 昨日放量10%以上阳线
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        # 判断昨日是否是阳线
        klines = self.cached[stock_code]['daily_bar']
        yesterday_close_price = klines.iloc[-1]['close']
        yesterday_open_price = klines.iloc[-1]['open']
        is_rise = yesterday_open_price < yesterday_close_price
        if not is_rise:
            return False
        
        # 判断昨日是否放量
        yesterday_volume = klines.iloc[-1]['volume'] # 昨日成交量
        before_yesterday_volume = klines.iloc[-2]['volume'] # 前日成交量
        volume_change_rate = (yesterday_volume - before_yesterday_volume) / before_yesterday_volume

        if volume_change_rate > 0.1:
            return True
        return False

    def _sell_signal_3(self, stock_code: str, bars: pd.DataFrame, fail_to_board_limit: float = 0.09) -> bool:
        """
        卖出信号3:
        1. 昨日涨停或跌停或上板失败
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        klines = self.cached[stock_code]['daily_bar']
        # 判断昨日是否涨、跌停
        is_limit_up = is_limit(stock_code, klines.iloc[-1]['close'], klines.iloc[-1]['preClose'])
        is_limit_down = is_limit(stock_code, klines.iloc[-1]['close'], klines.iloc[-1]['preClose'], 'down')
        # 判断昨日是否上板失败(昨日最高涨幅>=fail_to_board_limit,但收盘未涨停)
        is_fail_to_board = klines.iloc[-1]['high'] >= klines.iloc[-1]['preClose'] * (1 + fail_to_board_limit) and not is_limit_up

        if is_limit_up or is_limit_down or is_fail_to_board:
            return True
        return False

    def _sell_signal_4(self, stock_code: str, bars: pd.DataFrame, fail_to_board_limit: float = 0.09) -> bool:
        """
        卖出信号4:
        1. 今日上板失败
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        klines = self.cached[stock_code]['daily_bar']
        # 今日涨停价
        limit_price_up = get_limit_price(stock_code, klines.iloc[-1]['close'], 'up')
        # 昨日收盘价
        yesterday_close_price = klines.iloc[-1]['close']

        # 判断今日是否上板失败(今日最高涨幅>=fail_to_board_limit,但未涨停)
        highest_change_rate = (bars['high'].max() - yesterday_close_price) / yesterday_close_price
        if highest_change_rate >= fail_to_board_limit and bars.iloc[-1]['close'] < limit_price_up:
            return True
        return False
    
    def _sell_signal_5(self, stock_code: str, bars: pd.DataFrame, compare_top_price: bool = False) -> bool:
        """
        卖出信号4:
        1. 分时MACD顶点
        Args:
            stock_code: 股票代码
            bars: 分时K线快照，
            compare_top_price: 是否比较顶部顶点价格(默认不比较)
        Returns:
            bool: 是否符合
        """
        macd_data = get_macd(bars)
        if is_macd_top(macd_data):
            if compare_top_price:
                last_top_price = self.cached[stock_code].get('top_price', 0)
                # 判断当前价格是否低于上一个顶部顶点价格
                if bars.iloc[-1]['close'] < last_top_price or last_top_price == 0:
                    return True
            else:
                return True
        return False

    def _sell_signal_6(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号6:
        1. 分时炸板
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        klines = self.cached[stock_code]['daily_bar']
        # 今日涨停价
        limit_price_up = get_limit_price(stock_code, klines.iloc[-1]['close'], 'up')

        # 分时炸板
        if bars.iloc[-1]['high'] >= limit_price_up and bars.iloc[-1]['close'] < limit_price_up:
            return True
        return False
    
    def _sell_signal_7(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号7:
        1. 跌停
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        klines = self.cached[stock_code]['daily_bar']
        limit_price_down = get_limit_price(stock_code, klines.iloc[-1]['close'], 'down')
        # 当日分时最低价，触及跌停价
        if bars['low'].min() <= limit_price_down:
            return True
        return False
    
    def _sell_shield_signal(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出屏蔽信号:
        1. 当前涨停，不卖出
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        if is_limit(stock_code, bars.iloc[-1]['close'], bars.iloc[-1]['preClose']):
            return True
        return False