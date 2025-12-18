"""
双重动量突破策略
"""
from strategys.BaseStrategy import BaseStrategy
from utils.data import get_daily_bars
from typing import List, Optional, Dict
import pandas as pd
from laboratory.multipleK import get_ma, get_macd, is_macd_top, get_ma_list, is_macd_bottom, get_dynamic_daily_kline, get_boll
from laboratory.singleK import is_limit, get_limit_price
from utils.util import convert_to_safe_sell_volume, calculate_slope_polyfit

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
        index_daily_bars = get_daily_bars(stock_list=['000001.SH'], period="1d", end_time=trade_date, count=90, table_name='index_daily')
        # 计算大盘指数ma5斜率
        index_daily_bars_close_last_5 = index_daily_bars['000001.SH']['close'].iloc[-5:]
        index_slope = calculate_slope_polyfit(index_daily_bars_close_last_5)
        # 遍历个股，自选符合条件的股票
        result = []
        for stock_code, daily_bar in daily_bars.items():
            if self._select_stock(stock_code=stock_code, daily_bars=daily_bar, index_slope=index_slope):
                latest_close_price = daily_bar.iloc[-1]['close']
                if latest_close_price >= self.price_min and latest_close_price <= self.price_max:
                    result.append(stock_code)
        return result

    def _select_stock(self, stock_code: str, daily_bars: pd.DataFrame, index_slope: float) -> bool:
        """
        判断是否符合双重动量突破图形要求
        Args:
            stock_code: 股票代码
            daily_bars: 日K线数据框
            index_slope: 大盘指数斜率
        Returns:
            bool: 是否符合图形要求，True表示符合，False表示不符合
        图形要求：
        # 0. 判断最近15个交易日内是否有涨停板
        1. 近期趋势向下，最近一日站上5日线且5日线拐点向上
        2. 最近一日MACD趋势向上
        3. 突破5日均线不能是涨停或上板失败
        4. 大盘斜率不能为正数
        # 4. 个股近5日不能跑输大盘指数(个股近5日收盘价斜率 < 大盘指数斜率)
        # 5. 近5个交易日不能有贯穿boll下轨的情况
        # 6. 最近一日股价位于20日均线之上
        7. 最近一日股价不能突破boll上轨
        """
        # # 判断是否符合条件0（最近15个交易日内是否有涨停板）
        # if not is_exist_last_first_board(stock_code, daily_bars, 15):
        #     return False

        # 判断是否符合条件1（最近一日突破5日均线）
        ma_list = get_ma_list(daily_bars=daily_bars, period=5)
        # 兼容ma_list长度小于5的情况
        if len(ma_list) < 5:
            return False

        # 近期趋势向下
        is_trend_down = ma_list[-2] < ma_list[-3] < ma_list[-4] < ma_list[-5]
        # 最近一日站上5日线
        is_breakout_ma = daily_bars.iloc[-1]['close'] > ma_list[-1] and daily_bars.iloc[-2]['close'] < ma_list[-2]
        # 5日线拐点向上
        is_turn_up = ma_list[-1] > ma_list[-2]
        if not is_trend_down or not is_turn_up:
            return False

        is_breakout_ma = daily_bars.iloc[-1]['close'] > ma_list[-1] and daily_bars.iloc[-2]['close'] < ma_list[-2]
        if not is_breakout_ma:
            return False

        # 判断是否符合条件2（最近一日MACD趋势向上）
        macd_data = get_macd(daily_bars=daily_bars)
        is_macd_up = macd_data.iloc[-1]['macd'] > 0 and macd_data.iloc[-2]['macd'] < 0
        if not is_macd_up:
            return False
    
        # 判断是否符合条件3（突破5日均线不能是涨停或上板失败）
        is_limit_up = is_limit(stock_code, daily_bars.iloc[-1]['close'], daily_bars.iloc[-1]['preClose'])
        is_fail_to_board = daily_bars.iloc[-1]['high'] >= daily_bars.iloc[-1]['preClose'] * (1 + 0.08) and not is_limit_up
        if is_limit_up or is_fail_to_board:
            return False

        # 判断是否符合条件4（大盘斜率不能为正数）
        if index_slope > 0:
            return False

        # # 判断是否符合条件4（个股近5日斜率不能小于大盘指数近5日斜率）
        # daily_bars_close_last_5 = daily_bars['close'].iloc[-5:]
        # daily_bars_slope = calculate_slope_polyfit(daily_bars_close_last_5)
        # if daily_bars_slope < index_slope:
        #     return False

        # 判断是否符合条件5(近5根K线中是否存在贯穿boll下轨的情况)
        boll_data = get_boll(daily_bars=daily_bars, period=20).iloc[-5:]
        boll_data['is_break_boll_lower'] = boll_data['low'] < boll_data['boll_lower']
        if boll_data['is_break_boll_lower'].sum() > 0:
            return False
        return True

        # # 判断是否符合条件6（前一日股价位于20日均线之上）
        # ma_list = get_ma_list(daily_bars=daily_bars, period=20)
        # if daily_bars.iloc[-1]['close'] <= ma_list[-1]:
        #     return False
        
        # 判断是否符合条件7（最近一日股价不能突破boll上轨）
        if daily_bars.iloc[-1]['close'] > boll_data.iloc[-1]['boll_upper']:
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
        
        1. 开盘价格不低于昨日收盘价格（允许0.005误差）
        2. MACD底部顶点买入

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
        1. 开盘价格不低于昨日收盘价格（允许0.005误差）
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        klines = self.cached[stock_code]['daily_bar']
        # 昨日收盘价格
        yesterday_close_price = klines.iloc[-1]['close']
        # 开盘价格不低于昨日收盘价格（允许0.005误差）
        if bars.iloc[0]['open'] < yesterday_close_price * (1 - 0.005):
            return False
        return True
        
    def _buy_signal_2(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        买入信号2:
        1. MACD底部顶点买入
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        macd_data = get_macd(bars)
        if is_macd_bottom(macd_data):
            return True
        return False

    def sell_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        卖出信号生成
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        
        1. 昨日日线MACD为负向且当前动态MACD亦为负向
        2. 昨日放量30%以上阳线
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
        signal_2 = self._sell_signal_2(stock_code, bars, volume_change_rate=0.3)
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
                    'desc': f"组合1- （{int(signal_1)} | {int(signal_2)} | {int(signal_3)} | {int(signal_7)}） & {int(signal_5)}"
                }

        # 组合2： (4 or 6) and 5_2; 清仓卖出
        if (signal_4 or signal_6) and signal_5_2:
            return {
                'action': 'sell',
                'stock_code': stock_code,
                'price': bars.iloc[-1]['close'],
                'volume': available_volume,
                'time': bars.index[-1],
                'desc': f"组合2- （{int(signal_4)} | {int(signal_5)}） & {int(signal_5_2)}"
            }



    def _sell_signal_1(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号1:
        1. 当前动态MACD为负趋势
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        # 历史日K线
        klines = self.cached[stock_code]['daily_bar']
        # 构造动态日K线
        dynamic_daily_kline = get_dynamic_daily_kline(bars)
        # 合并历史日K线和动态日K线
        dynamic_klines = pd.concat([klines, dynamic_daily_kline], ignore_index=True)
        # 计算动态MACD
        macd_data = get_macd(dynamic_klines)
        # 判断当前动态MACD是否为负趋势
        if macd_data.iloc[-1]['macd'] < macd_data.iloc[-2]['macd']:
            return True
        return False
        

    def _sell_signal_2(self, stock_code: str, bars: pd.DataFrame, volume_change_rate: float = 0.2) -> bool:
        """
        卖出信号2:
        1. 昨日放量volume_change_rate以上阳线
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

        if volume_change_rate > volume_change_rate:
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