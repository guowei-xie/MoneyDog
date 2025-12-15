"""
N字战法-突破策略

策略概述：
    本策略基于"N字战法"理论，专注于在股票突破关键位置时进行买入操作，通过技术指标和量价关系
    识别突破买入时机，并在合适的时机卖出以获取收益。

策略原理：
    1. N字形态识别：寻找在放量后经过缩量整理，随后出现涨停的股票，形成"N"字形态
    2. 突破买入：在股票突破关键阻力位时买入，结合MACD底部、价格突破、涨幅控制和均线压制判断
    3. 技术卖出：结合多个技术指标和量价关系，在合适的时机分批或清仓卖出

选股条件：
    1. 股票价格区间：5元 - 60元
    2. 技术形态：放量后缩量整理，随后出现涨停（is_limit_board_after_volume_consolidation_v2，p=10）
    3. 股票池：主板股票

买入信号（以下条件全部符合）：
    信号1：分时MACD底部突破
        - 当前分时MACD位于底部顶点
        - 当前价格大于上一个底部顶点价格
        - 说明：用于确认价格在MACD底部反转后的上升趋势
    
    信号2：价格突破涨停后高点
        - 当前分时价格高于最近涨停日（包含涨停日）后的所有日线收盘价
        - 说明：确认价格已突破涨停后的整理区间
    
    信号3：涨幅控制
        - 当日涨幅位于2%~5%之间
        - 当日是阳线（收盘价 > 开盘价）
        - 说明：避免追高，选择温和上涨的时机
    
    信号4：无均线压制
        - 当前分时价格上方无均线（MA5、MA10、MA20、MA30）压制
        - 说明：动态计算均线，确保价格已突破所有关键均线
    
    买入逻辑：必须同时满足信号1、2、3、4才能买入
    
    买入屏蔽条件：
        - 当日内有过涨停（触及涨停价）
        - 或日内回落幅度超过5%（最高涨幅 - 当前涨幅 > 5%）

卖出信号：
    信号1：放量阳线
        - 昨日（非建仓日）放量10%以上阳线
        - 或昨日放量30%以上阳线（无论是否建仓日）
    
    信号2：异常波动
        - 昨日涨停或跌停
        - 或昨日上板失败（最高涨幅>=9%，但收盘未涨停）
    
    信号3：今日上板失败
        - 今日最高涨幅>=9%
        - 但当前价未达到涨停价
    
    信号4：分时MACD顶点
        - 分时MACD指标出现顶点
        - 可选条件：当前价格低于上一个顶部顶点价格（用于组合1）
    
    信号5：分时炸板
        - 当前分钟K线最高价 >= 涨停价
        - 当前价 < 涨停价（封板后开板）
    
    信号6：止损-跌破支撑
        - 当前价跌破最近15天内最后一个涨停日的收盘价
        - 说明：以涨停日收盘价作为支撑位
    
    信号7：止损-当天跌停
        - 当日分时最低价触及跌停价
    
    卖出逻辑：
        组合1：分批卖出
            - (信号1 或 信号2 或 信号6 或 信号7) 且 信号4（比较顶部价格）
            - 卖出数量 = 可用数量 / 剩余分批次数（默认2次）
        
        组合2：清仓卖出
            - 信号3 且 信号4（不比较顶部价格）
        
        组合3：清仓卖出
            - 信号5（炸板直接清仓）
    
    屏蔽条件：
        - 当前涨停时不卖出（保持持仓）

风险控制：
    1. 价格区间限制：仅选择5-60元区间的股票，避免低价股和过高价股
    2. 涨幅控制：买入时限制在2%-5%涨幅区间，避免追高
    3. 分批卖出：部分信号触发时采用分批卖出策略，降低一次性清仓风险
    4. 多重止损：设置跌破支撑位和跌停止损，及时止损保护资金
    5. 涨停保护：涨停时保持持仓，避免过早卖出
    6. 买入屏蔽：日内涨停或大幅回落时不买入，避免追高风险

技术指标说明：
    - MA4/MA9/MA19/MA29：4日、9日、19日、29日移动平均线
    - 动态MA5/MA10/MA20/MA30：实时计算的动态均线，包含当前价格
    - MACD：分时MACD指标，用于判断趋势底部和顶部
    - 成交量变化率：当日成交量相对前一日的变化比例
    - 涨停日：最近15天内最后一个涨停交易日

注意事项：
    1. 本策略基于历史数据回测，实际交易中需结合市场环境调整参数
    2. 动态均线的计算依赖于实时价格，需确保数据及时性
    3. 分时MACD底部和顶点判断需要足够的分时数据支持
    4. 分批卖出次数默认设置为2次，可根据实际情况调整
    5. 建议在实盘使用前进行充分的回测验证

"""
from pickle import FALSE
import pandas as pd
from typing import List, Dict, Optional
from utils.logger import info
from strategys.BaseStrategy import BaseStrategy
from utils.data import get_daily_bars
from utils.util import convert_to_safe_sell_volume
from laboratory.custom import is_limit_board_after_volume_consolidation_v2
from laboratory.multipleK import get_macd, is_macd_bottom, is_macd_top, get_last_limit_day, get_daily_bars_by_date, get_ma
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
        daily_bars = get_daily_bars(stock_list=self.global_stock_list, period="1d", end_time=trade_date, count=90)
        result = []
        for stock_code, daily_bar in daily_bars.items():
            if is_limit_board_after_volume_consolidation_v2(stock_code, daily_bar, p=10):
                latest_close_price = daily_bar.iloc[-1]['close']
                if latest_close_price >= self.price_min and latest_close_price <= self.price_max:
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