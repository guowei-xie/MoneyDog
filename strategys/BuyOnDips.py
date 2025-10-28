"""
买入在低点策略实现
"""
import time
import configparser
import pandas as pd

from utils.data import get_stock_list_in_main_board, get_trade_calendar, get_daily_bars, download_stock_history_data
from utils.logger import info, debug
from utils.util import generate_minute_snapshot, get_elapsed_time_str, add_num_date_days
from utils.broker import Broker
from laboratory.multipleK import get_last_limit_day_kline, get_ma, get_volume_change_rate, get_average_volume
from laboratory.custom import is_limit_board_after_volume_consolidation
from laboratory.singleK import get_limit_price, is_limit

config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

class BuyOnDips:
    def __init__(self):
        self.start_time = time.time()
        self.download_start_time = config.get('DOWNLOAD', 'download_start_time')
        self.download_required = config.get('DOWNLOAD', 'download_required')
        self.backtest_start_time = config.get('BACKTEST', 'backtest_start_time')
        self.backtest_end_time = config.get('BACKTEST', 'backtest_end_time')
        self.price_min = 5.0 # 价格区间选股：最低价格
        self.price_max = 60.0 # 价格区间选股：最高价格
        self.broker = Broker()

    def run(self) -> bool:
        """
        策略运行
        Returns:
            bool: 是否成功
        """
        self.prepare()
        for trade_date in self.trade_calendar:
            proceed = self.before_open(trade_date)
            if proceed:
                for minute_snapshot in self.minute_snapshots:
                    self.on_minute(minute_snapshot)
            self.after_close(trade_date)
            info("=" * 100)
        self.end_of_backtest()
        return True
        
    def prepare(self) -> bool:
        """
        准备策略运行环境：
        1. 获取交易日期列表
        2. 获取大盘股票池
        3. 如果下载配置为true，则下载历史日线数据
        4. 如果下载配置为true，则下载股票分时数据
        Returns:
            bool: 是否准备成功
        """
        
        # 1. 获取交易日期列表
        self.trade_calendar = get_trade_calendar(self.backtest_start_time, self.backtest_end_time)
        info(f"获取交易日期列表完成: {len(self.trade_calendar)} 天")
        
        # 2. 获取大盘股票池
        self.global_stock_list = get_stock_list_in_main_board()
        info(f"获取大盘股票池完成: {len(self.global_stock_list)} 只股票")

        # 3. 下载历史日线数据
        if self.download_required == "false":
            info(f"下载配置为false，跳过下载大盘股票池历史数据和分时数据")
            return True

        info(f"开始获取大盘股票池并下载历史数据")
        start_time = time.time()
        download_stock_history_data(self.global_stock_list, self.download_start_time, "1d", True)
        info(f"获取大盘股票池完成: {len(self.global_stock_list)} 只股票，耗时: {time.time() - start_time} 秒")

        # 4. 下载股票分时数据
        info(f"开始下载股票分时数据")
        start_time = time.time()
        download_stock_history_data(self.global_stock_list, self.download_start_time, "1m", True)
        info(f"下载股票分时数据完成: {len(self.global_stock_list)} 只股票，耗时: {time.time() - start_time} 秒")
        return True

    def before_open(self, trade_date: str) -> bool:
        """
        策略开盘前运行
        Args:
            trade_date: 交易日期
        1. 获取自选股票列表（预买入）
        2. 获取持仓股票列表（预卖出）
        3. 缓存盘前指标数据（备用于盘中运行）
        4. 获取当日分时线数据，并模拟分时快照数据
        Returns:
            bool: 是否成功
        """
        info(f"策略开盘前运行: 【{add_num_date_days(trade_date, 1)}】")
        # 资产概览
        info(f"可用资金: {self.broker.available_amount:,.2f} 元，持仓价值: {self.broker.get_position_value():,.2f} 元，总资产: {self.broker.get_total_assets():,.2f} 元, 总盈利率: {self.broker.get_total_profit_rate():,.2f}%")
        # 盘前清除volume为0的持仓股票信息、解锁昨日所有被锁定的持仓
        self.broker.clean_position()
        self.broker.unlock_position()
        
        # 1. 获取持仓股票列表（预卖出）
        self.holding_stock_list = self._get_holding_stock_list()

        # 2. 获取自选股票列表（预买入），过滤掉已经持仓的股票
        self.selected_stock_list = self._get_selected_stock_list(trade_date)
        self.selected_stock_list = [stock_code for stock_code in self.selected_stock_list if stock_code not in self.holding_stock_list]
        info(f"自选股票列表（预买入）: {self.selected_stock_list}")

        if not self.selected_stock_list and not self.holding_stock_list:
            info(f"没有自选股票和持仓股票，跳过策略开盘前运行")
            self.minute_snapshots = []
            return False

        # 3. 缓存盘前指标数据（备用于盘中运行）
        self._set_cached(trade_date)

        # 4. 获取当日股池的分时线行情数据，并模拟生成分时快照
        self.minute_snapshots = self._simulate_minute_daily(add_num_date_days(trade_date, 1) )
        
        return True

    def _get_selected_stock_list(self, trade_date: str) -> list:
        """
        获取自选股票列表（预买入）
        Args:
            trade_date: 交易日期
        Returns:
            list: 自选股票列表
        """
        daily_bars = get_daily_bars(stock_list=self.global_stock_list, period="1d", end_time=trade_date, count=30)
        result = []
        for stock_code, daily_bar in daily_bars.items():
            if is_limit_board_after_volume_consolidation(stock_code, daily_bar):
                if daily_bar.iloc[-1]['close'] >= self.price_min and daily_bar.iloc[-1]['close'] <= self.price_max:
                    result.append(stock_code)
        info(f"获取自选股票列表（预买入）完成: {len(result)} 只股票")
        debug(f"自选股票列表: {result}")
        return result
    
    def _get_holding_stock_list(self) -> list:
        """
        获取持仓股票列表（预卖出）
        Returns:
            list: 持仓股票列表
        """
        positions = self.broker.positions
        result = []
        # 检查每个持仓，volume大于0的才是实际持仓
        for stock_code, position in positions.items():
            if position.get('volume', 0) > 0:
                result.append(stock_code)
        info(f"获取持仓股票列表（预卖出）完成: {len(result)} 只股票")
        info(f"持仓股票列表: {result}")
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

        # 缓存大盘数据

        # 缓存个股数据
        for stock_code, daily_bar in daily_bars.items():
            # 获取建仓日
            build_date = self.broker.get_build_date(stock_code)
            # 建仓日前的涨停交易日K线数据
            if build_date:
                before_build_limit_day_kline = get_last_limit_day_kline(stock_code, daily_bar.loc[:build_date], 5)
            else:
                before_build_limit_day_kline = pd.DataFrame()

            # 获取日成交量变化率
            volume_change_rate = get_volume_change_rate(daily_bar)
            # 获取日均成交量
            average_volume = get_average_volume(daily_bar)
            # 缓存个股数据
            self.cached[stock_code] = {
                'daily_bar': daily_bar, # 日K线数据
                'limit_price_up': get_limit_price(stock_code, daily_bar.iloc[-1]['close'], 'up'), # 当日涨停价格
                'limit_price_down': get_limit_price(stock_code, daily_bar.iloc[-1]['close'], 'down'), # 当日跌停价格
                'day_ma4': get_ma(daily_bars=daily_bar, period=4), # 4日均价线
                'day_ma9': get_ma(daily_bars=daily_bar, period=9), # 9日均价线
                'build_date': build_date, # 建仓日期
                'cost_price': self.broker.get_position_cost_price(stock_code), # 持仓成本
                'before_build_limit_day_kline': before_build_limit_day_kline, # 建仓日前的涨停交易日K线数据
                'volume': daily_bar.iloc[-1]['volume'], # 昨日成交量
                'volume_change_rate': volume_change_rate.iloc[-1]['volume_change_rate'], # 昨日成交量变化率
                'average_volume': average_volume.iloc[-2]['average_volume'], # 前日日均成交量
                'is_limit_up': is_limit(stock_code, daily_bar.iloc[-1]['close'], daily_bar.iloc[-1]['preClose'], 'up'), # 昨日是否涨停
            }


        return True

    def _simulate_minute_daily(self, trade_date: str) -> list:
        """
        模拟分时快照数据（每分钟累积数据）
        Args:
            trade_date: 交易日期
        Returns:
            list: 各股票各分钟的快照数据 [{'minute': minute, 'snapshot': [{'stock_code': stock_code, 'bars': bars}]}]
        """
        stock_list = self.selected_stock_list + self.holding_stock_list
        daily_bars = get_daily_bars(stock_list, "1m", trade_date, trade_date, count=-1)
        snapshots = generate_minute_snapshot(daily_bars)
        return snapshots
    
    def on_minute(self, snapshot: dict) -> bool:
        """
        策略盘中分时线运行
        Args:
            snapshot: 行情快照 {'minute': minute, 'snapshot': [{'stock_code': stock_code, 'bars': bars}]}
        Returns:
            bool: 是否成功
        """
        for item in snapshot['snapshot']:
            stock_code = item.get('stock_code')
            bars = item.get('bars')
            if not stock_code or bars is None:
                continue
            if stock_code in self.selected_stock_list:
                signal = self._buy_signal(stock_code, bars)
            elif stock_code in self.holding_stock_list:
                signal = self._sell_signal(stock_code, bars)
            else:
                continue
            if signal is not None:
                self.trade(signal)
        return True

    def _buy_signal(self, stock_code: str, bars: pd.DataFrame) -> dict:
        """
        买入信号:
        1. 动态ma5价格大于最低价（含误差）
        2. 开盘价大于动态ma5价格
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            dict: 买入信号 {'action': 'buy', 'stock_code': stock_code, 'price': price, 'volume': volume, 'time': time}
        """
        # 判断是否已持仓
        if stock_code in self.broker.positions:
            return None

        # 动态ma5 = (ma4 * 4 + 当前价 )/ 5
        day_ma4 = self.cached[stock_code]['day_ma4']
        dynamic_ma5 = (day_ma4 * 4 + bars.iloc[-1]['close']) / 5

        # 开盘价（即第一根K线开盘价）
        open_price = bars.iloc[0]['open']

        # 最低价（含误差）
        error = 0.005
        low_price = bars.iloc[-1]['low'] * (1 - error)

        if dynamic_ma5 >= low_price and open_price >= dynamic_ma5:
            
            buy_price = bars.iloc[-1]['close']
            return {
                'action': 'buy',
                'stock_code': stock_code,
                'price': buy_price,
                'volume': 100,
                'time': bars.index[-1],
                'desc': f"动态ma5价格买入",
                'detail': f"动态ma5价格: {dynamic_ma5}, 最低价（含误差）: {low_price}, 开盘价: {open_price}, ma4: {day_ma4}"
            }
        return None

    def _sell_signal(self, stock_code: str, bars: pd.DataFrame) -> dict:
        """
        卖出信号: 
        1. 低于MA10价格
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
            dict: 卖出信号 {'action': 'sell', 'stock_code': stock_code, 'price': price, 'volume': volume, 'time': time}
        """
        # 屏蔽信号：当前涨停，不卖出
        if self._shield_signal(stock_code, bars):
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
            desc = f"卖出信号: {' '.join(['1' if x else '0' for x in signals])}"

            return {
                'action': 'sell',
                'stock_code': stock_code,
                'price': bars.iloc[-1]['close'],
                'volume': 100,
                'time': bars.index[-1],
                'desc': desc
            }
        return None

    def _sell_signal_1(self, stock_code: str, bars: pd.DataFrame) -> dict:
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
    
    def _sell_signal_2(self, stock_code: str, bars: pd.DataFrame) -> dict:
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
    
    def _sell_signal_3(self, stock_code: str, bars: pd.DataFrame) -> dict:
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
    
    def _sell_signal_4(self, stock_code: str, bars: pd.DataFrame) -> dict:
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

    def _sell_signal_5(self, stock_code: str, bars: pd.DataFrame) -> dict:
        """
        卖出信号5:
        1. 分时MACD顶点
        Args:
            stock_code: 股票代码
            bars: 分时K线快照
        Returns:
            bool: 是否符合
        """

        # 测试
        if len(bars) == 235:
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

    # 屏蔽信号：当前涨停，不卖出
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

    def trade(self, signal: dict) -> bool:
        """
        交易
        Args:
            signal: 交易信号执行动作
        Returns:
            bool: 是否成功
        """
        if signal['action'] == 'buy':
            self.broker.buy(signal)
        elif signal['action'] == 'sell':
            self.broker.sell(signal)

        return True

    def after_close(self, trade_date: str) -> bool:
        """
        每日收盘后运行
        Args:
            trade_date: 交易日期
        Returns:
            bool: 是否成功
        """
        if self.minute_snapshots:
            minute_snapshot = self.minute_snapshots[-1]
            self.broker.update_position(minute_snapshot)
        else:
            info(f"没有分时快照数据，跳过盘后更新持仓信息")

        self.broker.record_position_and_account_change(trade_date)

        return True

    def end_of_backtest(self) -> bool:
        """
        回测结束
        Returns:
            bool: 是否成功
        """
        self.broker.download_transactions()
        self.broker.analyze_result()
        info(f"回测结束，运行耗时: {get_elapsed_time_str(self.start_time)}")
        return True