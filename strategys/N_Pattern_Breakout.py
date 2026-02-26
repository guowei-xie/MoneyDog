"""
N字战法-突破策略
策略描述见：strategys/N_Pattern_Breakout.md
"""
import pandas as pd
from typing import List, Dict, Optional
from utils.logger import info
from strategys.BaseStrategy import BaseStrategy
from utils.data import get_daily_bars
from utils.util import convert_to_safe_sell_volume
from laboratory.custom import is_exist_one_board, is_exist_t_board
from laboratory.multipleK import get_macd, is_macd_bottom, is_macd_top, get_last_limit_day, get_daily_bars_by_date, get_ma, get_max_volume, is_volume_decreasing, get_limit_board_number
from laboratory.singleK import is_limit, get_limit_price

class NPatternBreakout(BaseStrategy):
    """
    N字战法-突破策略
    """

    def __init__(self):
        """
        初始化策略
        """
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
        daily_bars = self.get_daily_bars_for_selection(trade_date, 90)
        result = []
        for stock_code, daily_bar in daily_bars.items():
            if self._select_stock(stock_code=stock_code, daily_bars=daily_bar, p=10):
                latest_close_price = daily_bar.iloc[-1]['close']
                if latest_close_price >= self.price_min and latest_close_price <= self.price_max:
                    result.append(stock_code)
        return result

    def _select_stock(self, stock_code: str, daily_bars: pd.DataFrame, n: int = 5, m: int = 10, k: int = 2, r: float = 0.9, p: int = 10, l: float = -0.03, h: float = 0.1, w: float = 0.05) -> bool:
        """
        判断是否符合涨停后缩量盘整图形要求
        Args:
            stock_code: 股票代码
            daily_bars: 日K线数据框
            n: 最近{n}个交易日内存在涨停板，且最近一次涨停最多是二板
            m: 最近{m}个交易日内不能存在一字板
            k: 最近{k}个交易日不能是涨停板
        Returns:
            bool: 是否符合图形要求，True表示符合，False表示不符合
        图形要求：
        1. 近{n}个交易日内存在涨停板，且最近一次涨停最多是二板
        2. 近{m}个交易日内不能存在一字板
        3. 最近一次涨停日至少早于当前{k}个交易日
        4. 最近的涨停日次日的成交量不低于涨停日的{r} 且不低于最近{p}日最大成交量
        5. 最近的涨停日次日至今，成交量逐日递减
        6. 最近的涨停日次日至今，日内震荡幅度处于涨停日价格的{l}~{h}之间
        7. 最近1日振幅小于{w}
        8. 最近的涨停日是MACD金叉日
        """
        # 判断是否符合条件1（最近一次涨停最多是二板）
        last_limit_day = get_last_limit_day(stock_code, daily_bars, n)
        if last_limit_day == -1:
            return False
        
        daily_bars_last = daily_bars.loc[:last_limit_day].copy()
        limit_board_number = get_limit_board_number(stock_code, daily_bars_last)
        if limit_board_number == 0 or limit_board_number > 2:
            return False

        # 判断是否符合条件2（近{m}个交易日内不能存在一字板或T字板）
        if is_exist_one_board(stock_code, daily_bars, m) or is_exist_t_board(stock_code, daily_bars, m):
            return False

        # 判断是否符合条件3（最近一次涨停日至少早于当前{k}个交易日）
        daily_bars = get_max_volume(daily_bars, period=p)
        focused_bars = get_daily_bars_by_date(daily_bars, start_date=last_limit_day, end_date=daily_bars.index[-1])
        if len(focused_bars) <= k:
            return False

        # 判断是否符合条件4（最近的涨停日次日的成交量不低于涨停日的{r} 且不低于近10日最大成交量）
        volume_ratio = focused_bars['volume'].iloc[1] / focused_bars['volume'].iloc[0]
        max_volume_ratio = focused_bars['volume'].iloc[1] / focused_bars['max_volume'].iloc[0]
        if volume_ratio < r or max_volume_ratio < 1:
            return False

        # 判断是否符合条件5（最近的涨停日次日至今，成交量逐日递减）
        if not is_volume_decreasing(focused_bars.iloc[1:]):
            return False

        # 判断是否符合条件6（最近的涨停日次日至今，日内震荡幅度处于涨停日价格的{l}~{h}之间）
        limit_price = focused_bars.iloc[0]['close']
        lowest_price = focused_bars.iloc[1:]['low'].min()
        highest_price = focused_bars.iloc[1:]['high'].max()
        if lowest_price / limit_price - 1 < l or highest_price / limit_price - 1 > h:
            return False

        # 判断是否符合条件7（最近1日振幅小于{w}）
        if focused_bars.iloc[-1]['high'] / focused_bars.iloc[-1]['low'] - 1 >= w:
            return False

        # 判断是否符合条件8（最近的涨停日是MACD金叉日）
        macd_data = get_macd(daily_bars=daily_bars_last)
        # is_macd_gold_cross = macd_data.iloc[-1]['macd'] > 0 and macd_data.iloc[-2]['macd'] < 0
        is_macd_gold_cross = macd_data.iloc[-2]['macd'] < 0 and macd_data.iloc[-2]['macd'] >  macd_data.iloc[-3]['macd']
        # is_macd_gold_cross = macd_data.iloc[-2]['macd'] < 0 
        if not is_macd_gold_cross:
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
            # 获取最近涨停日（包含涨停日）后的距今区间K线(用于判断是否符合买入信号2)
            last_limit_day = get_last_limit_day(stock_code, daily_bar, 5)
            if last_limit_day != -1:
                last_limit_day_range_klines = get_daily_bars_by_date(daily_bar, start_date=last_limit_day, end_date=daily_bar.index[-1])
                self.cached[stock_code]['last_limit_day_range_klines'] = last_limit_day_range_klines
                # 缓存盘中所需的静态数据（避免盘中重复计算）
                # 最近涨停日（包含涨停日）后的距今的最高收盘价（用于判断是否符合买入信号2）
                last_limit_day_range_highest_close_price = last_limit_day_range_klines['close'].max()
                self.cached[stock_code]['last_limit_day_range_highest_close_price'] = last_limit_day_range_highest_close_price
            # 均线数据（用于判断是否符合买入信号4）
            self.cached[stock_code]['ma4'] = get_ma(daily_bars=daily_bar, period=4)
            self.cached[stock_code]['ma9'] = get_ma(daily_bars=daily_bar, period=9)
            self.cached[stock_code]['ma19'] = get_ma(daily_bars=daily_bar, period=19)
            self.cached[stock_code]['ma29'] = get_ma(daily_bars=daily_bar, period=29)

            # 剩余卖出分批次数
            self.cached[stock_code]['batch_sell_count'] = self.batch_sell_count
        return True

    def buy_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        买入信号(以下条件全部符合):
        
        1. 当前分时MACD位于底部顶点且价格大于上一个底部顶点价格
        2. 当前分时价格高于最近涨停日（包含涨停日）后的所有日线收盘价
        3. 当日涨幅位于2%~5%之间且是阳线
        4. 当前分时价格上方无均线（MA5、MA10、MA20、MA30）压制

        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            Optional[Dict]: 买入信号 {'action': 'buy', 'stock_code': stock_code, 'price': price, 'volume': volume, 'time': time, 'desc': desc}，无信号返回None
        """
        # 判断是否已持仓
        if stock_code in self.broker.positions:
            return None

        # 买入信号(以下条件全部符合)
        signal_1 = self._buy_signal_1(stock_code, bars)
        if not signal_1:
            return None
        signal_2 = self._buy_signal_2(stock_code, bars)
        if not signal_2:
            return None
        signal_3 = self._buy_signal_3(stock_code, bars)
        if not signal_3:
            return None
        signal_4 = self._buy_signal_4(stock_code, bars)
        if not signal_4:
            return None

        # 买入屏蔽信号
        if self._buy_shield_signal(stock_code, bars):
            return None

        buy_price = bars.iloc[-1]['close']
        buy_volume = self.broker.get_buy_volume(buy_price)
        if buy_volume > 0:
            return {
                'action': 'buy',
                'stock_code': stock_code,
                'price': buy_price,
                'volume': buy_volume,
                'minute_k_count': len(bars),
                'time': bars.index[-1],
                'desc': f"信号:{int(signal_1)}{int(signal_2)}{int(signal_3)}{int(signal_4)}"
            }
        else:
            info(f"可用资金不足，无法买入: {stock_code} 可用资金: {self.broker.available_amount}, 需求: {buy_price * buy_volume}")
            return None
        return None

    def _buy_signal_1(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        买入信号1:
        1. 当前分时MACD位于底部顶点且价格大于上一个底部顶点价格
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        macd_data = get_macd(bars)
        if is_macd_bottom(macd_data):
            # 获取上一个底部顶点价格，无则返回0
            last_bottom_price = self.cached[stock_code].get('bottom_price', 0)
            # 更新底部顶点价格
            self.cached[stock_code]['bottom_price'] = bars.iloc[-1]['close']
            # 判断当前价格是否大于上一个底部顶点价格且上一个底部顶点价格不为0
            if bars.iloc[-1]['close'] > last_bottom_price and last_bottom_price != 0:
                return True
        return False

    def _buy_signal_2(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        买入信号2:
        1. 当前分时价格高于最近涨停日（包含涨停日）后的所有日线收盘价
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        if bars.iloc[-1]['close'] > self.cached[stock_code]['last_limit_day_range_highest_close_price']:
            return True
        return False

    def _buy_signal_3(self, stock_code: str, bars: pd.DataFrame, lwr_limit: float = 0.02, upr_limit: float = 0.05) -> bool:
        """
        买入信号3:
        1. 当日涨幅位于lwr_limit%~upr_limit%之间
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
            lwr_limit: 下限涨幅
            upr_limit: 上限涨幅
        Returns:
            bool: 是否符合
        """
        # 获取昨日收盘价
        klines = self.cached[stock_code]['last_limit_day_range_klines']
        yesterday_close_price = klines.iloc[-1]['close']

        # 判断是否是阳线
        is_rise = bars.iloc[-1]['close'] > bars.iloc[0]['open']
        # 判断是否在涨幅范围内
        is_limit = bars.iloc[-1]['close'] > yesterday_close_price * (1 + lwr_limit) and bars.iloc[-1]['close'] < yesterday_close_price * (1 + upr_limit)

        if is_rise and is_limit:
            return True
        return False

    def _buy_signal_4(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        买入信号4:
        1. 当前分时价格上方无均线（MA5、MA10、MA20、MA30）压制
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        ma5 = (self.cached[stock_code]['ma4'] * 4 + bars.iloc[-1]['close']) / 5
        ma10 = (self.cached[stock_code]['ma9'] * 9 + bars.iloc[-1]['close']) / 10
        ma20 = (self.cached[stock_code]['ma19'] * 19 + bars.iloc[-1]['close']) / 20
        ma30 = (self.cached[stock_code]['ma29'] * 29 + bars.iloc[-1]['close']) / 30
        if bars.iloc[-1]['close'] > ma5 and bars.iloc[-1]['close'] > ma10 and bars.iloc[-1]['close'] > ma20 and bars.iloc[-1]['close'] > ma30:
            return True
        return False
    
    def _buy_shield_signal(self, stock_code: str, bars: pd.DataFrame, drop_limit: float = 0.05) -> bool:
        f"""
        买入屏蔽信号:
        1. 当日内有过涨停，或回落幅度{drop_limit}以上
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        klines = self.cached[stock_code]['daily_bar']
        limit_price_up = get_limit_price(stock_code, klines.iloc[-1]['close'], 'up')
        pre_close_price = klines.iloc[-1]['close']
        # 日内炸板
        if bars['high'].max() >= limit_price_up:
            return True
        # 回落幅度超过drop_limit
        highest_rate = (bars['high'].max() - pre_close_price) / pre_close_price
        close_rate = (bars['close'].iloc[-1] - pre_close_price) / pre_close_price
        drop_rate = highest_rate - close_rate
        if drop_rate > drop_limit:
            return True
        return False

    def sell_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        卖出信号:
        1. 昨日放量10%以上阳线且当前盈利
        2. 昨日涨停或跌停或上板失败
        3. 今日上板失败
        4. 分时MACD顶点（可选条件：是否低于上一个顶部顶点价格）
        5. 炸板
        6. 止损-跌破支撑（20日均线）
        7. 止损-当天跌停
        信号组合：（1 or 2 or 6 or 7) and 4; 3 and 4; 5

        屏蔽信号：当前涨停，不卖出

        Args:
            stock_code: 股票代码
            bars: 分时K线快照
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
        signal_4 = self._sell_signal_4(stock_code, bars, compare_top_price=True)
        signal_4_2 = self._sell_signal_4(stock_code, bars)
        signal_5 = self._sell_signal_5(stock_code, bars)
        signal_6 = self._sell_signal_6(stock_code, bars)
        signal_7 = self._sell_signal_7(stock_code, bars)

        # 组合1： (1 or 2 or 6) and 4; 分批卖出
        if (signal_1 or signal_2 or signal_6 or signal_7) and signal_4:
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
                    'minute_k_count': len(bars),
                    'time': bars.index[-1],
                    'desc': f"组合1: （{int(signal_1)} | {int(signal_2)} | {int(signal_6)} | {int(signal_7)}） & {int(signal_4)}"
                }

        # 组合2： 3 and 4_2; 清仓卖出
        if signal_3 and signal_4_2:
            return {
                'action': 'sell',
                'stock_code': stock_code,
                'price': bars.iloc[-1]['close'],
                'volume': available_volume,
                'minute_k_count': len(bars),
                'time': bars.index[-1],
                'desc': f"组合2: {int(signal_3)} & {int(signal_4_2)}"
            }
        
        # 组合3： 5; 清仓卖出
        if signal_5:
            return {
                'action': 'sell',
                'stock_code': stock_code,
                'price': bars.iloc[-1]['close'],
                'volume': available_volume,
                'minute_k_count': len(bars),
                'time': bars.index[-1],
                'desc': f"组合3: {int(signal_5)}"
            }

        return None

    def _sell_signal_1(self, stock_code: str, bars: pd.DataFrame, change_rate: float = 0.1) -> bool:
        """
        卖出信号1:
        1. 昨日（非建仓日）放量change_rate以上阳线且当前盈利
        2. 或昨日放量20%以上阳线且当前盈利
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
            change_rate: 放量变化率
        Returns:
            bool: 是否符合
        """
        # # 获取持仓成本
        # cost_price = self.broker.get_position_cost_price(stock_code)
        # # 判断当前价格是否高于持仓成本
        # if bars.iloc[-1]['close'] < cost_price:
        #     return False

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

        # 判断昨日是否是建仓日
        build_date = self.broker.get_build_date(stock_code)
        is_build_day = build_date == klines.index[-1]

        if volume_change_rate > change_rate and not is_build_day:
            return True
        
        if volume_change_rate > 0.3:
            return True
        return False

    def _sell_signal_2(self, stock_code: str, bars: pd.DataFrame, fail_to_board_limit: float = 0.09) -> bool:
        """
        卖出信号2:
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

    def _sell_signal_3(self, stock_code: str, bars: pd.DataFrame, fail_to_board_limit: float = 0.09) -> bool:
        """
        卖出信号3:
        1. 今日上板失败
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
            fail_to_board_limit: 上板失败涨幅限制(日内最高涨幅>=fail_to_board_limit,但未涨停)
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

    def _sell_signal_4(self, stock_code: str, bars: pd.DataFrame, compare_top_price: bool = False) -> bool:
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
                # 更新顶部顶点价格
                self.cached[stock_code]['top_price'] = bars.iloc[-1]['close']
                # 判断当前价格是否低于上一个顶部顶点价格
                if bars.iloc[-1]['close'] < last_top_price or last_top_price == 0:
                    return True
            else:
                return True
        return False

    def _sell_signal_5(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号5:
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

    def _sell_signal_6(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号6:
        1. 止损(价格跌破20日均线)或上个涨停日收盘价
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """
        # ma20 = (self.cached[stock_code]['ma19'] * 19 + bars.iloc[-1]['close']) / 20
        # if bars.iloc[-1]['close'] < ma20:
        #     return True

        klines = self.cached[stock_code]['daily_bar']
        laste_limit_day = get_last_limit_day(stock_code, klines, 15)
        if laste_limit_day != -1:
            last_limit_day_close_price = klines.loc[laste_limit_day]['close']
            if bars.iloc[-1]['close'] < last_limit_day_close_price:
                return True

        return False


    def _sell_signal_7(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        卖出信号7:
        1. 止损-当天有过跌停
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
        屏蔽信号:
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