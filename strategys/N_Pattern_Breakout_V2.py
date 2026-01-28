"""
N字战法-突破策略V2
"""

from strategys.BaseStrategy import BaseStrategy

from typing import List, Dict, Optional
from utils.data import get_daily_bars
from utils.logger import debug
import pandas as pd
from laboratory.multipleK import (
    get_last_limit_day,
    get_limit_board_number,
    is_volume_decreasing,
    get_ma5_top,
    get_macd,
    is_macd_bottom,
    get_dynamic_daily_kline,
)
from laboratory.singleK import is_limit
from utils.logger import info

class NPatternBreakoutV2(BaseStrategy):
    """
    N字战法-突破策略V2
    """
    def __init__(self):
        """
        初始化策略
        """
        super().__init__()
        # 价格区间选股配置
        self.price_min = 5.0  # 价格区间选股：最低价格
        self.price_max = 100.0  # 价格区间选股：最高价格
        
        # 卖出配置
        self.batch_sell_count = 2  # 卖出时分批次数
        
        # 选股条件配置
        self.limit_check_days = 5  # 近N个交易日内存在涨停板
        self.max_limit_board = 2  # 最多N板（首板或二板）
        self.min_days_after_limit = 3  # 最新交易日距离T日 >= N 个交易日
        self.volume_check_days = 20  # 近N日最大成交量检查
        self.amplitude_check_days = 20  # 近N日区间振幅检查
        self.max_amplitude = 0.5  # 最大振幅（最高价/最低价-1）
        self.limit_count_check_days = 250  # 近N个交易日（约1年）统计涨停次数
        self.min_limit_count = 5  # 近1年涨停次数 >= N次
        self.daily_bars_count = 260  # 获取日K数据条数（用于满足近1年涨停次数判断）
        
        # 买入信号配置
        self.t_day_price_range = 0.06  # T日收盘价波动范围（±6%）
        self.max_daily_change_rate = 0.08  # 当日最高涨幅限制（8%）

    def get_selected_stock_list(self, trade_date: str) -> List[str]:
        """
        获取自选股票列表（预买入）
        
        Args:
            trade_date (str): 交易日期
        
        Returns:
            List[str]: 自选股票代码列表
        """
        # 为满足「近1年涨停次数」判断，这里获取约1年的日K数据
        daily_bars = get_daily_bars(stock_list=self.global_stock_list, period="1d", end_time=trade_date, count=self.daily_bars_count)
        result = []
        for stock_code, daily_bar in daily_bars.items():
            if self._select_stock(stock_code=stock_code, daily_bars=daily_bar):
                result.append(stock_code)
        return result

    def _select_stock(self, stock_code: str, daily_bars: pd.DataFrame) -> bool:
        """
        判断是否符合N字战法V2的选股条件
        1. 近N个交易日内存在涨停板，且是首板或N板，最新涨停日为T日（可配置：limit_check_days, max_limit_board）
        2. 最新交易日距离T日>=N个交易日（可配置：min_days_after_limit）
        3. T+1日成交量是近N日最大成交量（可配置：volume_check_days）
        4. T+1日至最新交易日，成交量逐日递减
        5. 自T日起，收盘价均不低于最近一次ma5顶部价格
        6. 近N日区间振幅<=M%（可配置：amplitude_check_days, max_amplitude）
        7. 近N个交易日涨停次数>=M次（可配置：limit_count_check_days, min_limit_count）

        Args:
            stock_code: 股票代码
            daily_bars: 日K线数据框
        Returns:
            bool: 是否符合选股条件
        """
        if daily_bars is None or daily_bars.empty:
            return False
        
        # 价格过滤：当前价格必须在指定区间内
        latest_close_price = daily_bars.iloc[-1]['close']
        if latest_close_price < self.price_min or latest_close_price > self.price_max:
            return False

        # 1. 近N个交易日内存在涨停板，且是首板或二板，最新涨停日为T日
        last_limit_day = get_last_limit_day(stock_code, daily_bars, n=self.limit_check_days)
        if last_limit_day == -1:
            return False

        # 判断最近一次涨停是几板（最多N板）
        daily_bars_until_T = daily_bars.loc[:last_limit_day].copy()
        limit_board_number = get_limit_board_number(stock_code, daily_bars_until_T)
        if limit_board_number == 0 or limit_board_number > self.max_limit_board:
            return False

        # 2. 最新交易日距离T日 >= N 个交易日
        focused_bars = daily_bars.loc[last_limit_day:daily_bars.index[-1]].copy()
        if len(focused_bars) <= self.min_days_after_limit:
            return False

        # 3. T+1 日成交量是近 N 日最大成交量
        # 需要至少 2 根K线（T 和 T+1）
        if len(daily_bars) < 2:
            return False
        # 近N日样本
        recent_n = daily_bars.iloc[-self.volume_check_days:].copy() if len(daily_bars) >= self.volume_check_days else daily_bars.copy()
        max_volume_n = recent_n["volume"].max()
        # T+1 日的成交量
        try:
            t1_bar = focused_bars.iloc[1]
        except IndexError:
            return False
        if t1_bar["volume"] < max_volume_n:
            return False

        # 4. T+1 日至最新交易日，成交量逐日递减
        if not is_volume_decreasing(focused_bars.iloc[1:]):
            return False

        # 5. 自 T 日起，收盘价均不低于最近一次 MA5 顶部「均线」价格
        # 先计算 MA5 顶部形态
        ma5_top_df = get_ma5_top(daily_bars)
        # 仅保留被标记为 MA5 顶部的交易日
        ma5_top_df = ma5_top_df[ma5_top_df["is_ma5_top"]]
        # 只考虑发生在 T 日之前的 MA5 顶部（最近一次顶部）
        ma5_top_df = ma5_top_df[ma5_top_df.index < last_limit_day]
        
        if ma5_top_df.empty:
            return False
        # 最近一次 MA5 顶点所在行
        last_ma5_top_row = ma5_top_df.iloc[-1]
        # 使用 MA5 均线值作为顶部价格，而不是 K 线收盘价
        last_ma5_top_price = last_ma5_top_row["ma5"]
        # 从 T 日起所有收盘价都不能跌破该 MA5 顶部价格
        if daily_bars.loc[last_limit_day:]["close"].min() < last_ma5_top_price:
            return False

        # 6. 近 N 日区间振幅 <= M%（最高价/最低价 - 1）
        if len(daily_bars) < self.amplitude_check_days:
            return False
        last_n = daily_bars.iloc[-self.amplitude_check_days:]
        highest_price = last_n["high"].max()
        lowest_price = last_n["low"].min()
        if lowest_price <= 0:
            return False
        amplitude = highest_price / lowest_price - 1
        if amplitude > self.max_amplitude:
            return False

        # 7. 近 N 个交易日涨停次数 >= M 次
        # 说明：
        # - 这里使用 self.get_selected_stock_list 中预先获取的日K数据，足以覆盖近 1 年交易日
        # - 如数据条数不足配置天数，则在已有数据范围内统计涨停次数
        if len(daily_bars) >= self.limit_count_check_days:
            last_n_days = daily_bars.iloc[-self.limit_count_check_days:]
        else:
            last_n_days = daily_bars

        limit_up_count = 0
        for _, row in last_n_days.iterrows():
            # 使用通用单K工具函数判断是否涨停
            if is_limit(stock_code, row["close"], row["preClose"]):
                limit_up_count += 1

        if limit_up_count < self.min_limit_count:
            return False

        # 所有条件满足，标记为符合选股条件
        debug(f"NPatternBreakoutV2 选股命中: {stock_code}")
        return True

    def set_cached(self, trade_date: str) -> bool:
        """
        缓存盘前数据（备用于盘中运行）
        
        Args:
            trade_date (str): 交易日期
        
        Returns:
            bool: 是否缓存成功
        """
        self.cached = {}
        stock_list = self.selected_stock_list + self.holding_stock_list
        if not stock_list:
            return True
        
        daily_bars = get_daily_bars(stock_list, "1d", start_time="", end_time=trade_date, count=60)
        for stock_code, daily_bar in daily_bars.items():
            self.cached[stock_code] = {}
            self.cached[stock_code]['daily_bar'] = daily_bar
            
            # 获取T日（涨停日）收盘价
            last_limit_day = get_last_limit_day(stock_code, daily_bar, n=self.limit_check_days)
            if last_limit_day != -1:
                t_day_close = daily_bar.loc[last_limit_day]['close']
                self.cached[stock_code]['t_day_close'] = t_day_close
            else:
                self.cached[stock_code]['t_day_close'] = None
            
            # 获取最近一次MA5顶部价格
            ma5_top_df = get_ma5_top(daily_bar)
            ma5_top_df = ma5_top_df[ma5_top_df["is_ma5_top"]]
            if not ma5_top_df.empty:
                last_ma5_top_price = ma5_top_df.iloc[-1]["ma5"]
                self.cached[stock_code]['last_ma5_top_price'] = last_ma5_top_price
            else:
                self.cached[stock_code]['last_ma5_top_price'] = None
        
        return True

    def buy_signal(self, stock_code: str, bars) -> Optional[Dict]:
        """
        生成买入信号:
        1. 当前在日内分时MACD底部
        2. 当前动态日线MACD为红柱且高于昨日
        3. 当日最高价格突破过昨日实体上沿价格
        4. 当前价格不低于最近一次MA5顶部价格
        5. 当前价格位于T日收盘价±N%之间（可配置：t_day_price_range）
        6. 当前价格不低于分时均价
        7. 当日最高涨幅应小于N%（可配置：max_daily_change_rate）
        
        Args:
            stock_code (str): 股票代码
            bars: 分时K线快照数据（DataFrame）
        
        Returns:
            Optional[Dict]: 买入信号字典，无信号返回 None
        """
        # 判断是否已持仓
        if stock_code in self.broker.positions:
            return None
        
        # 检查缓存数据
        if stock_code not in self.cached or 'daily_bar' not in self.cached[stock_code]:
            return None
        
        daily_bar = self.cached[stock_code]['daily_bar']
        if daily_bar is None or daily_bar.empty or len(daily_bar) < 2:
            return None
        
        current_price = bars.iloc[-1]['close']
        current_high = bars['high'].max()
        
        # 1. 当前在日内分时MACD底部
        macd_data = get_macd(bars)
        if not is_macd_bottom(macd_data):
            return None
        
        # 2. 当前动态日线MACD为红柱且高于昨日
        dynamic_daily_kline = get_dynamic_daily_kline(bars)
        if dynamic_daily_kline.empty:
            return None
        dynamic_klines = pd.concat([daily_bar, dynamic_daily_kline], ignore_index=True)
        dynamic_macd = get_macd(dynamic_klines)
        if len(dynamic_macd) < 2:
            return None
        today_macd = dynamic_macd.iloc[-1]['macd']
        yesterday_macd = dynamic_macd.iloc[-2]['macd']
        if today_macd <= 0 or today_macd <= yesterday_macd:
            return None
        
        # 3. 当日最高价格突破过昨日实体上沿价格
        yesterday_bar = daily_bar.iloc[-1]
        yesterday_entity_top = max(yesterday_bar['open'], yesterday_bar['close'])
        if current_high <= yesterday_entity_top:
            return None
        
        # 4. 当前价格不低于最近一次MA5顶部价格
        last_ma5_top_price = self.cached[stock_code].get('last_ma5_top_price')
        if last_ma5_top_price is None or current_price < last_ma5_top_price:
            return None
        
        # 5. 当前价格位于T日收盘价±N%之间
        t_day_close = self.cached[stock_code].get('t_day_close')
        if t_day_close is None:
            return None
        price_lower = t_day_close * (1 - self.t_day_price_range)
        price_upper = t_day_close * (1 + self.t_day_price_range)
        if current_price < price_lower or current_price > price_upper:
            return None
        
        # 6. 当前价格不低于分时均价（成交量加权平均价）
        total_amount = bars['amount'].sum()
        total_volume = bars['volume'].sum()
        if total_volume > 0:
            avg_price = total_amount / total_volume
            if current_price < avg_price:
                return None
        
        # 7. 当日最高涨幅应小于N%
        yesterday_close = yesterday_bar['close']
        max_change_rate = (current_high - yesterday_close) / yesterday_close
        if max_change_rate >= self.max_daily_change_rate:
            return None
        
        # 所有条件满足，生成买入信号
        buy_volume = self.broker.get_buy_volume(current_price)
        if buy_volume > 0:
            return {
                'action': 'buy',
                'stock_code': stock_code,
                'price': current_price,
                'volume': buy_volume,
                'time': bars.index[-1],
                'desc': 'N字战法V2买入信号'
            }
        else:
            info(f"可用资金不足，无法买入: {stock_code}")
            return None

    def sell_signal(self, stock_code: str, bars) -> Optional[Dict]:
        """
        生成卖出信号
        
        Args:
            stock_code (str): 股票代码
            bars: 分时K线快照数据（DataFrame）
        
        Returns:
            Optional[Dict]: 卖出信号字典，无信号返回 None
        """
        # TODO: 实现卖出信号逻辑
        # 当前仅为占位实现
        return None
