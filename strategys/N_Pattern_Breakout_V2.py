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
    is_macd_top,
    get_dynamic_daily_kline,
)
from laboratory.singleK import is_limit
from utils.logger import info
from laboratory.singleK import get_limit_price
from utils.util import convert_to_safe_sell_volume

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
        self.sell_macd_min_bars = 5  # MACD 顶点/底部判定所需最少分时K线数量
        self.sell_broken_limit_gap_minutes = 3  # 炸板判定：距离最近一次封板的分钟数 >= N（3分钟未回封）
        self.sell_yesterday_max_change_rate = 0.08  # 组合A条件：昨日最大涨幅阈值（>=8%）
        self.sell_intraday_max_change_rate = 0.09  # 组合A条件：日内最大涨幅阈值（>=9%）
        self.sell_volume_expand_rate_normal = 0.10  # 组合A条件：非建仓日昨日成交量放大阈值（>=10%）
        self.sell_volume_expand_rate_build_day = 0.30  # 组合A条件：建仓日昨日成交量放大阈值（>=30%）
        
        # 选股条件配置
        self.limit_check_days = 5  # 近N个交易日内存在涨停板
        self.max_limit_board = 2  # 最多N板（首板或二板）
        self.min_days_after_limit = 3  # 最新交易日距离T日 >= N 个交易日
        self.volume_check_days = 20  # 近N日最大成交量检查
        self.amplitude_check_days = 20  # 近N日区间振幅检查
        self.max_amplitude = 0.5  # 最大振幅（最高价/最低价-1）
        self.limit_count_check_days = 250  # 近N个交易日（约1年）统计涨停次数
        self.min_limit_count = 6  # 近1年涨停次数 >= N次
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
            # 分批卖出剩余次数（默认每天盘前重置）
            self.cached[stock_code]['batch_sell_count'] = self.batch_sell_count
            # 分时MACD顶部记录：用于卖出信号里做“上一个顶点”对比
            self.cached[stock_code]['top_price'] = 0.0
            self.cached[stock_code]['top_macd'] = 0.0
            
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

    def on_minute_end(self, stock_code: str, bars: pd.DataFrame):
        """
        分钟结束时更新盘中缓存数据。

        目前用于：记录分时 MACD 顶点（价格/指标值），为后续“比较上一次顶点/顶背离”提供依据。

        Args:
            stock_code (str): 股票代码
            bars (pd.DataFrame): 分时K线快照数据
        """
        if stock_code not in self.cached:
            return
        if bars is None or getattr(bars, "empty", True) or len(bars) < self.sell_macd_min_bars:
            return

        macd_data = get_macd(bars)
        if is_macd_top(macd_data):
            self._update_top_cache(
                stock_code=stock_code,
                top_price=float(bars.iloc[-1]['close']),
                top_macd=float(macd_data.iloc[-1]['macd']),
            )

    def buy_signal(self, stock_code: str, bars) -> Optional[Dict]:
        """
        生成买入信号:
        （按计算成本由低到高检测）
        1. 不在持仓中，且分时/缓存数据完备
        2. 当前价 >= 最近一次 MA5 顶部价（盘前缓存）
        3. 当前价在 T 日收盘价 ±N%（可配置：t_day_price_range）
        4. 当日最高价突破昨日实体上沿
        5. 当日最高涨幅 < N%（可配置：max_daily_change_rate）
        6. 当前价 >= 分时均价（成交量加权均价）
        7. 分时 MACD 底部
        8. 动态日线 MACD 红柱且高于昨日
        
        Args:
            stock_code (str): 股票代码
            bars: 分时K线快照数据（DataFrame）
        
        Returns:
            Optional[Dict]: 买入信号字典，无信号返回 None
        """
        # 0) 持仓过滤
        if stock_code in self.broker.positions:
            return None

        # 0) 数据完备性校验
        if bars is None or getattr(bars, "empty", True):
            return None
        if len(bars) < 1:
            return None
        
        # 0) 缓存校验
        if stock_code not in self.cached or 'daily_bar' not in self.cached[stock_code]:
            return None
        
        daily_bar = self.cached[stock_code]['daily_bar']
        if daily_bar is None or daily_bar.empty or len(daily_bar) < 2:
            return None
        
        current_price = bars.iloc[-1]['close']

        # 1) 当前价 >= 最近一次 MA5 顶部价（缓存）
        last_ma5_top_price = self.cached[stock_code].get('last_ma5_top_price')
        if last_ma5_top_price is None or current_price < last_ma5_top_price:
            return None

        # 2) 当前价在 T 日收盘价 ±N%（缓存）
        t_day_close = self.cached[stock_code].get('t_day_close')
        if t_day_close is None:
            return None
        price_lower = t_day_close * (1 - self.t_day_price_range)
        price_upper = t_day_close * (1 + self.t_day_price_range)
        if current_price < price_lower or current_price > price_upper:
            return None

        # 3) 准备昨日数据（用于突破/涨幅）
        yesterday_bar = daily_bar.iloc[-1]
        yesterday_close = yesterday_bar['close']

        # 3) 当日最高价（复用）
        current_high = bars['high'].max()

        # 3) 当日最高价突破昨日实体上沿
        yesterday_entity_top = max(yesterday_bar['open'], yesterday_bar['close'])
        if current_high <= yesterday_entity_top:
            return None

        # 4) 最高涨幅 < N%
        if yesterday_close <= 0:
            return None
        max_change_rate = (current_high - yesterday_close) / yesterday_close
        if max_change_rate >= self.max_daily_change_rate:
            return None

        # 5) 当前价 >= 分时均价（成交量加权均价）
        total_volume = bars['volume'].sum()
        if total_volume > 0:
            total_amount = bars['amount'].sum()
            avg_price = total_amount / total_volume / 100
            if current_price < avg_price:
                return None

        # 6) 分时 MACD 底部
        macd_data = get_macd(bars)
        if not is_macd_bottom(macd_data):
            return None

        # 7) 动态日线 MACD 红柱且高于昨日
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
        
        # 所有条件满足，生成买入信号
        buy_volume = self.broker.get_buy_volume(current_price)
        if buy_volume > 0:
            return {
                'action': 'buy',
                'stock_code': stock_code,
                'price': current_price,
                'volume': buy_volume,
                'time': bars.index[-1],
                'desc': ''
            }
        else:
            info(f"可用资金不足，无法买入: {stock_code}")
            return None

    def _check_macd_top_gate(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict[str, float]]:
        """
        分时 MACD 顶点过滤（卖出触发的必要条件）。

        满足：
        1) 分时 MACD 出现顶点（`is_macd_top`）
        2) 且符合以下任一：
           - 日内首次出现（无上一次顶点记录）
           - 低于上一个顶点价格
           - 顶背离：价格不低于上一次顶点价，但 MACD 柱值低于上一次顶点 MACD

        Args:
            stock_code (str): 股票代码
            bars (pd.DataFrame): 分时K线快照

        Returns:
            Optional[Dict[str, float]]: 通过时返回 {current_price, current_macd, last_top_price, last_top_macd}；否则返回 None
        """
        if bars is None or getattr(bars, "empty", True) or len(bars) < self.sell_macd_min_bars:
            return None

        current_price = float(bars.iloc[-1]['close'])
        macd_data = get_macd(bars)
        if not is_macd_top(macd_data):
            return None

        current_macd = float(macd_data.iloc[-1]['macd'])
        last_top_price = float(self.cached[stock_code].get('top_price', 0.0) or 0.0)
        last_top_macd = float(self.cached[stock_code].get('top_macd', 0.0) or 0.0)

        is_first_top = last_top_price <= 0
        is_lower_than_last_top = (last_top_price > 0 and current_price < last_top_price)
        # 顶背离（内联）：价格不低于上次顶点，但 MACD 弱于上次顶点
        is_divergence = (last_top_price > 0 and last_top_macd != 0 and current_price >= last_top_price and current_macd < last_top_macd)

        if not (is_first_top or is_lower_than_last_top or is_divergence):
            return None

        return {
            'current_price': current_price,
            'current_macd': current_macd,
            'last_top_price': last_top_price,
            'last_top_macd': last_top_macd,
        }

    def _update_top_cache(self, stock_code: str, top_price: float, top_macd: float):
        """
        更新分时 MACD 顶点缓存（用于后续“比较上一次顶点/顶背离”）。

        Args:
            stock_code (str): 股票代码
            top_price (float): 顶点价格（本策略用当前分钟收盘价）
            top_macd (float): 顶点 MACD 柱值
        """
        self.cached[stock_code]['top_price'] = float(top_price)
        self.cached[stock_code]['top_macd'] = float(top_macd)

    def _get_sell_volume_by_batch(self, stock_code: str, available_volume: int) -> int:
        """
        按“剩余分批次数”计算本次卖出数量，并返回安全委托数量（100整数倍）。

        Args:
            stock_code (str): 股票代码
            available_volume (int): 当前可用可卖数量

        Returns:
            int: 本次卖出数量（0表示不卖）
        """
        batch_sell_count = int(self.cached[stock_code].get('batch_sell_count', self.batch_sell_count) or self.batch_sell_count)
        batch_sell_count = max(batch_sell_count, 1)
        plan_sell_volume = available_volume / batch_sell_count
        return int(convert_to_safe_sell_volume(plan_sell_volume, available_volume))

    def _sell_combo_b_broken_limit(self, stock_code: str, bars: pd.DataFrame, yesterday_close: float, available_volume: int) -> Optional[Dict]:
        """
        组合B：炸板清仓（3分钟未回封）。

        Args:
            stock_code (str): 股票代码
            bars (pd.DataFrame): 分时K线快照
            yesterday_close (float): 昨日收盘价（用于计算涨停价）
            available_volume (int): 可卖数量

        Returns:
            Optional[Dict]: 卖出信号，无信号返回 None
        """
        current_price = float(bars.iloc[-1]['close'])
        limit_price_up = float(get_limit_price(stock_code, yesterday_close, 'up'))
        is_hit_limit = (bars['high'].max() >= limit_price_up)
        if not (is_hit_limit and current_price < limit_price_up):
            return None

        limit_close_idx = bars.index[bars['close'] >= limit_price_up]
        if len(limit_close_idx) <= 0:
            return None

        last_limit_pos = int(bars.index.get_loc(limit_close_idx[-1]))
        gap = (len(bars) - 1) - last_limit_pos
        if gap < self.sell_broken_limit_gap_minutes:
            return None

        info(f"{stock_code} 触发炸板清仓: gap={gap}")
        return {
            'action': 'sell',
            'stock_code': stock_code,
            'price': current_price,
            'volume': int(available_volume),
            'time': bars.index[-1],
            'desc': '止盈（炸板）'
        }

    def _sell_combo_a_take_profit(self, stock_code: str, bars: pd.DataFrame, daily_bar: pd.DataFrame, available_volume: int, top_ctx: Dict[str, float]) -> Optional[Dict]:
        """
        组合A：分批止盈卖出。

        条件：
        - 当前盈利
        - 且满足（昨日最大涨幅>=8% / 昨日成交量放大（建仓日30%否则10%）/ 日内最大涨幅>=9%）之一
        - 且满足 MACD 顶点过滤（由 top_ctx 表示）
        """
        current_price = float(top_ctx['current_price'])
        current_macd = float(top_ctx['current_macd'])

        cost_price = float(self.broker.get_position_cost_price(stock_code))
        if not (cost_price > 0 and current_price > cost_price):
            return None

        yesterday_bar = daily_bar.iloc[-1]
        yesterday_close = float(yesterday_bar['close'])
        yesterday_pre_close = float(yesterday_bar['preClose'])
        yesterday_max_change = (float(yesterday_bar['high']) - yesterday_pre_close) / yesterday_pre_close if yesterday_pre_close > 0 else 0.0

        prev_bar = daily_bar.iloc[-2]
        prev_volume = float(prev_bar['volume'])
        yesterday_volume = float(yesterday_bar['volume'])
        volume_change_rate = (yesterday_volume - prev_volume) / prev_volume if prev_volume > 0 else 0.0

        build_date = self.broker.get_build_date(stock_code)
        yesterday_date = str(daily_bar.index[-1]).replace('-', '').replace(' ', '')[:8]
        volume_threshold = self.sell_volume_expand_rate_build_day if (build_date and build_date == yesterday_date) else self.sell_volume_expand_rate_normal
        is_yesterday_volume_expand = volume_change_rate >= volume_threshold

        intraday_high = float(bars['high'].max())
        intraday_max_change = (intraday_high - yesterday_close) / yesterday_close if yesterday_close > 0 else 0.0

        cond2 = (
            yesterday_max_change >= self.sell_yesterday_max_change_rate
            or is_yesterday_volume_expand
            or intraday_max_change >= self.sell_intraday_max_change_rate
        )
        if not cond2:
            return None

        sell_volume = self._get_sell_volume_by_batch(stock_code, int(available_volume))
        if sell_volume <= 0:
            return None

        self.cached[stock_code]['batch_sell_count'] = max(int(self.cached[stock_code].get('batch_sell_count', self.batch_sell_count)) - 1, 0)
        self._update_top_cache(stock_code, current_price, current_macd)
        # info(f"{stock_code} 触发分批止盈卖出: vol={sell_volume}, remain={self.cached[stock_code]['batch_sell_count']}")
        return {
            'action': 'sell',
            'stock_code': stock_code,
            'price': current_price,
            'volume': int(sell_volume),
            'time': bars.index[-1],
            'desc': '止盈（常规）'
        }

    def _sell_combo_c_stop_loss(self, stock_code: str, bars: pd.DataFrame, available_volume: int, top_ctx: Dict[str, float]) -> Optional[Dict]:
        """
        组合C：分批止损卖出（跌破 MA5 顶部支撑 + MACD 顶点过滤）。
        """
        support_price = self.cached[stock_code].get('last_ma5_top_price')
        if support_price is None:
            return None

        current_price = float(top_ctx['current_price'])
        current_macd = float(top_ctx['current_macd'])
        if current_price >= float(support_price):
            return None

        sell_volume = self._get_sell_volume_by_batch(stock_code, int(available_volume))
        if sell_volume <= 0:
            return None

        self.cached[stock_code]['batch_sell_count'] = max(int(self.cached[stock_code].get('batch_sell_count', self.batch_sell_count)) - 1, 0)
        self._update_top_cache(stock_code, current_price, current_macd)
        # info(f"{stock_code} 触发分批止损卖出: close={current_price}, support={support_price}, vol={sell_volume}")
        return {
            'action': 'sell',
            'stock_code': stock_code,
            'price': current_price,
            'volume': int(sell_volume),
            'time': bars.index[-1],
            'desc': '止损（常规）'
        }

    def sell_signal(self, stock_code: str, bars) -> Optional[Dict]:
        """
        生成卖出信号(基于条件组合，当任意组合命中时，卖出；卖出方式分为分批卖出和清仓卖出)

        若当前涨停，则不卖出，否则执行以下组合：

        组合A（分批止盈卖出）：
            1. 当前盈利
            2. 且符合以下任意条件：
                - 昨日最大涨幅>=8%
                - 昨日（非建仓日）成交量放大10%以上
                - 昨日（是建仓日）成交量放大30%以上
                - 日内最大涨幅>=9%
            3. 且当分时MACD出现顶点，并且符合以下任意条件：
                - 日内首次出现
                - 低于上一个顶点价格
                - 发生顶背离（不低于上个顶点价格，但MACD值小于上个顶点MACD值）
        
        组合B（清仓止盈卖出）:
            1. 炸板（3分钟未回封，即间隔最近一根涨停k线数量>=3）

        组合C（分批止损卖出）:
            1. 以最近一次MA5顶部价格作为支撑位，跌破支撑位
            2. 且当分时MACD出现顶点，并且符合以下任意条件：
                - 日内首次出现
                - 低于上一个顶点价格
                - 发生顶背离（不低于上个顶点价格，但MACD值小于上个顶点MACD值）
            

        Args:
            stock_code (str): 股票代码
            bars: 分时K线快照数据（DataFrame）
        
        Returns:
            Optional[Dict]: 卖出信号字典，无信号返回 None
        """
        # 0) 持仓过滤
        if stock_code not in self.broker.positions:
            return None
        if bars is None or getattr(bars, "empty", True) or len(bars) < self.sell_macd_min_bars:
            return None
        if stock_code not in self.cached or 'daily_bar' not in self.cached[stock_code]:
            return None

        daily_bar = self.cached[stock_code]['daily_bar']
        if daily_bar is None or daily_bar.empty or len(daily_bar) < 2:
            return None

        available_volume = int(self.broker.get_available_volume(stock_code))
        if available_volume <= 0:
            return None

        # 昨日数据（用于涨停保护、涨幅、成交量）
        yesterday_bar = daily_bar.iloc[-1]
        yesterday_close = float(yesterday_bar['close'])
        current_price = float(bars.iloc[-1]['close'])

        # 屏蔽：当前涨停，不卖出
        if is_limit(stock_code, current_price, yesterday_close):
            return None

        # 1) 组合B：炸板清仓（优先级最高，不依赖MACD顶点）
        signal_b = self._sell_combo_b_broken_limit(stock_code, bars, yesterday_close, available_volume)
        if signal_b is not None:
            return signal_b

        # 2) MACD 顶点过滤（A/C 都需要）
        top_ctx = self._check_macd_top_gate(stock_code, bars)
        if top_ctx is None:
            return None

        # 3) 组合A：分批止盈
        signal_a = self._sell_combo_a_take_profit(stock_code, bars, daily_bar, available_volume, top_ctx)
        if signal_a is not None:
            return signal_a

        # 4) 组合C：分批止损
        signal_c = self._sell_combo_c_stop_loss(stock_code, bars, available_volume, top_ctx)
        if signal_c is not None:
            return signal_c

        return None
