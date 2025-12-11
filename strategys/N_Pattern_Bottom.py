"""
N字战法-低吸策略

策略概述：
    本策略基于"N字战法"理论，专注于在股票回调低点进行买入操作，通过技术指标和量价关系
    识别买入时机，并在合适的时机卖出以获取收益。

策略原理：
    1. N字形态识别：寻找在放量后经过缩量整理，随后出现涨停的股票，形成"N"字形态
    2. 低吸买入：在股票回调至关键均线附近时买入，利用动态均线判断低点
    3. 技术卖出：结合多个技术指标和量价关系，在合适的时机卖出

选股条件：
    1. 股票价格区间：5元 - 60元
    2. 技术形态：放量后缩量整理，随后出现涨停（is_limit_board_after_volume_consolidation）
    3. 股票池：主板股票

买入信号：
    信号1：动态MA5低吸
        - 动态MA5价格 >= 最低价（含0.5%误差）
        - 开盘价 >= 动态MA5价格
        - 说明：动态MA5 = (MA4 * 4 + 当前价) / 5
    
    信号2：动态MA10低吸
        - 动态MA10价格 >= 最低价（含0.5%误差）
        - 开盘价 >= 动态MA10价格 且 开盘价 < 动态MA5价格
        - 说明：动态MA10 = (MA9 * 9 + 当前价) / 10
    
    买入逻辑：满足信号1或信号2任一条件即可买入

卖出信号：
    信号1：跌破动态MA10
        - 当前价 < 动态MA10价格
    
    信号2：放量异常
        - 昨日成交量变化率 > 10%
        - 昨日成交量 > 近5日平均成交量
    
    信号3：昨日涨停
        - 昨日收盘价达到涨停价
    
    信号4：上板失败
        - 当日最高价 >= 涨停价 * 1.09（接近涨停）
        - 当前价 < 涨停价（未能封板）
    
    信号5：分时MACD顶点
        - 分时MACD指标出现顶点（is_macd_top）
    
    信号6：分时炸板
        - 当前分钟K线开盘价 >= 涨停价
        - 当前价 < 涨停价（封板后开板）
    
    卖出逻辑：
        - (信号1 或 信号2 或 信号3 或 信号4) 且 信号5
        - 或 信号6（炸板直接卖出）
    
    屏蔽条件：
        - 当前涨停时不卖出（保持持仓）

风险控制：
    1. 价格区间限制：仅选择5-60元区间的股票，避免低价股和过高价股
    2. 动态均线跟踪：使用动态均线判断，更贴近实时价格变化
    3. 多重卖出条件：结合多个技术指标，提高卖出信号的可靠性
    4. 涨停保护：涨停时保持持仓，避免过早卖出

技术指标说明：
    - MA4/MA9：4日和9日移动平均线
    - 动态MA5/MA10：实时计算的动态均线，包含当前价格
    - MACD：分时MACD指标，用于判断趋势顶点
    - 成交量变化率：当日成交量相对前一日的变化比例

注意事项：
    1. 本策略基于历史数据回测，实际交易中需结合市场环境调整参数
    2. 动态均线的计算依赖于实时价格，需确保数据及时性
    3. 分时MACD顶点判断需要足够的分时数据支持
    4. 建议在实盘使用前进行充分的回测验证

"""
import pandas as pd
from typing import List, Dict, Optional

from utils.data import get_daily_bars
from utils.logger import info, debug
from strategys.BaseStrategy import BaseStrategy
from laboratory.multipleK import get_last_limit_day_kline, get_ma, get_volume_change_rate, get_average_volume, get_macd, is_macd_top
from laboratory.custom import is_limit_board_after_volume_consolidation
from laboratory.singleK import get_limit_price, is_limit


class NPatternBottom(BaseStrategy):
    """
    N字战法-低吸策略
    """
    
    def __init__(self):
        """
        初始化策略
        """
        super().__init__()
        self.price_min = 5.0  # 价格区间选股：最低价格
        self.price_max = 60.0  # 价格区间选股：最高价格

    def _get_selected_stock_list(self, trade_date: str) -> List[str]:
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
            if is_limit_board_after_volume_consolidation(stock_code, daily_bar):
                latest_close_price = daily_bar.iloc[-1]['close']
                if latest_close_price >= self.price_min and latest_close_price <= self.price_max:
                    result.append(stock_code)
                    
        info(f"获取自选股票列表（预买入）完成: {len(result)} 只股票")
        debug(f"自选股票列表: {result}")
        return result

    def _set_cached(self, trade_date: str) -> bool:
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

        # 缓存个股数据
        for stock_code, daily_bar in daily_bars.items():
            # 获取建仓日
            build_date = self.broker.get_build_date(stock_code)
            # 建仓日前的涨停交易日K线数据
            if build_date:
                before_build_limit_day_kline = get_last_limit_day_kline(stock_code, daily_bar.loc[:build_date], 5)
            else:
                before_build_limit_day_kline = pd.DataFrame()
            
            # 获取最近5天内的最后一次涨停日K线
            last_limit_day_kline = get_last_limit_day_kline(stock_code, daily_bar, 5)

            # 获取日成交量变化率
            volume_change_rate = get_volume_change_rate(daily_bar)
            # 获取日均成交量
            average_volume = get_average_volume(daily_bar, period=3)
            # 缓存个股数据
            self.cached[stock_code] = {
                'daily_bar': daily_bar,  # 日K线数据
                'limit_price_up': get_limit_price(stock_code, daily_bar.iloc[-1]['close'], 'up'),  # 当日涨停价格
                'limit_price_down': get_limit_price(stock_code, daily_bar.iloc[-1]['close'], 'down'),  # 当日跌停价格
                'day_ma4': get_ma(daily_bars=daily_bar, period=4),  # 4日均价线
                'day_ma9': get_ma(daily_bars=daily_bar, period=9),  # 9日均价线
                'build_date': build_date,  # 建仓日期
                'cost_price': self.broker.get_position_cost_price(stock_code),  # 持仓成本
                'before_build_limit_day_kline': before_build_limit_day_kline,  # 已建仓票的建仓日前的涨停交易日K线数据
                'last_limit_day_kline': last_limit_day_kline,  # 最近5天内的最后一次涨停日K线数据
                'volume': daily_bar.iloc[-1]['volume'],  # 昨日成交量
                'volume_change_rate': volume_change_rate.iloc[-1]['volume_change_rate'],  # 昨日成交量变化率
                'average_volume': average_volume.iloc[-2]['average_volume'],  # 前日日均成交量
                'is_limit_up': is_limit(stock_code, daily_bar.iloc[-1]['close'], daily_bar.iloc[-1]['preClose'], 'up'),  # 昨日是否涨停
            }

        return True

    def _buy_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        买入信号:
        1. 动态ma5价格大于最低价（含误差）
        2. 开盘价大于动态ma5价格
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            Optional[Dict]: 买入信号 {'action': 'buy', 'stock_code': stock_code, 'price': price, 'volume': volume, 'time': time, 'desc': desc}，无信号返回None
        """
        # 判断是否已持仓
        if stock_code in self.broker.positions:
            return None

        # 动态ma5 = (ma4 * 4 + 当前价 )/ 5
        day_ma4 = self.cached[stock_code]['day_ma4']
        dynamic_ma5 = (day_ma4 * 4 + bars.iloc[-1]['close']) / 5
        # 动态ma10 = (ma9 * 9 + 当前价 )/ 10
        day_ma9 = self.cached[stock_code]['day_ma9']
        dynamic_ma10 = (day_ma9 * 9 + bars.iloc[-1]['close']) / 10
        # 获取最近5天内的最后一次涨停日收盘价
        last_limit_day_close_price = self.cached[stock_code]['last_limit_day_kline'].iloc[-1]['close']
        # 开盘价（即第一根K线开盘价）
        open_price = bars.iloc[0]['open']
        # 历史K线数据
        history_kline = self.cached[stock_code]['daily_bar']
        # 最新日收盘价
        latest_close_price = history_kline.iloc[-1]['close']

        # 最低价（含误差）
        error = 0.005
        low_price = bars.iloc[-1]['low'] * (1 - error)

        signal_1 = dynamic_ma5 >= low_price and open_price >= dynamic_ma5
        signal_2 = dynamic_ma10 >= low_price and open_price >= dynamic_ma10 and open_price < dynamic_ma5
        # signal_3 = last_limit_day_close_price >= low_price and open_price > last_limit_day_close_price * 1.01 and open_price >= latest_close_price  # 比最近涨停价高1%,且相对昨日高开，且不低于最新日收盘价

        if signal_1 or signal_2:
            buy_price = bars.iloc[-1]['close']
            buy_volume = self.broker.get_buy_volume(buy_price)

            if buy_volume > 0:
                return {
                    'action': 'buy',
                    'stock_code': stock_code,
                    'price': buy_price,
                    'volume': buy_volume,
                    'time': bars.index[-1],
                    'desc': f"信号{' '.join(['1' if x else '0' for x in [signal_1, signal_2]])}"
                }
            else:
                info(f"可用资金不足，无法买入: {stock_code} 可用资金: {self.broker.available_amount}, 需求: {buy_price * buy_volume}")
                return None
        return None

    def _sell_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        卖出信号: 
        1. 低于MA10价格且在分时均价线之下（待完成）
        2. 昨日放量10%以上且高于近5日平均成交量
        3. 昨日涨停
        4. 今日上板失败
        5. 分时MACD顶点
        6. 分时炸板
        (1 或 2 或 3 或 4) 且 5； 或 6

        屏蔽信号：当前涨停，不卖出
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            Optional[Dict]: 卖出信号 {'action': 'sell', 'stock_code': stock_code, 'price': price, 'volume': volume, 'time': time, 'desc': desc}，无信号返回None
        """
        # 屏蔽信号：当前涨停，不卖出
        if self._shield_signal(stock_code, bars):
            return None

        # 获取当前可用仓位，如果可用仓位为0，则无法卖出
        available_volume = self.broker.get_available_volume(stock_code)
        if available_volume <= 0:
            return None

        # 卖出信号1: 低于动态MA10价格
        signal_1 = self._sell_signal_1(stock_code, bars)
        signal_2 = self._sell_signal_2(stock_code, bars)
        signal_3 = self._sell_signal_3(stock_code, bars)
        signal_4 = self._sell_signal_4(stock_code, bars)
        signal_5 = self._sell_signal_5(stock_code, bars)
        signal_6 = self._sell_signal_6(stock_code, bars)

        # 逻辑判断：(1 或 2 或 3 或 4) 且 5； 或 6
        signals = [bool(signal_1), bool(signal_2), bool(signal_3), bool(signal_4), bool(signal_5), bool(signal_6)]
        if (any(signals[:4]) and signals[4]) or signals[5]:
            # 用0或1表示信号，例如101010，表示信号1、3、5符合
            desc = f"信号{' '.join(['1' if x else '0' for x in signals])}"
            # 获取可卖出数量
            sell_volume = self.broker.get_available_volume(stock_code)
            if sell_volume > 0:
                return {
                    'action': 'sell',
                    'stock_code': stock_code,
                    'price': bars.iloc[-1]['close'],
                    'volume': sell_volume,
                    'time': bars.index[-1],
                    'desc': desc
                }
            else:
                info(f"可用仓位不足，无法卖出: {stock_code} 可用仓位: {sell_volume}")
                return None
        return None

    def _sell_signal_1(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号1:
        1. 低于动态MA10价格
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        day_ma9 = self.cached[stock_code]['day_ma9']
        dynamic_ma10 = (day_ma9 * 9 + bars.iloc[-1]['close']) / 10
        if bars.iloc[-1]['close'] < dynamic_ma10:
            return True
        return False
    
    def _sell_signal_2(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号2:
        1. 昨日放量10%以上且高于近5日平均成交量
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        volume = self.cached[stock_code]['volume']
        volume_change_rate = self.cached[stock_code]['volume_change_rate']
        average_volume = self.cached[stock_code]['average_volume']
        if volume_change_rate > 0.1 and volume > average_volume:
            return True
        return False
    
    def _sell_signal_3(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号3:
        1. 昨日涨停
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        is_limit_up = self.cached[stock_code]['is_limit_up']
        if is_limit_up:
            return True
        return False
    
    def _sell_signal_4(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号4:
        1. 今日上板失败(即当日最高价大于9%，但最新价低于涨停价)
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        limit_price_up = self.cached[stock_code]['limit_price_up']
        if bars['high'].max() >= limit_price_up * 1.09 and bars.iloc[-1]['close'] < limit_price_up:
            return True
        return False

    def _sell_signal_5(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号5:
        1. 分时MACD顶点
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        macd_data = get_macd(bars)
        if is_macd_top(macd_data):
            return True
        return False

    def _sell_signal_6(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号6:
        1. 分时炸板（当前分钟K线开盘价等于涨停价，但最新价低于涨停价）
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        limit_price_up = self.cached[stock_code]['limit_price_up']
        if bars.iloc[-1]['open'] >= limit_price_up and bars.iloc[-1]['close'] < limit_price_up:
            return True
        return False

    def _shield_signal(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        屏蔽信号:
        1. 当前涨停，不卖出
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        limit_price_up = self.cached[stock_code]['limit_price_up']
        if bars.iloc[-1]['close'] >= limit_price_up:
            return True
        return False
