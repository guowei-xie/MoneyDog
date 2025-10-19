"""
买入在低点策略实现
"""
from utils.data import get_stock_list_in_main_board, download_stock_history_data
from utils.data import get_trade_calendar
from utils.data import get_daily_bars
from utils.logger import info, debug
from utils.util import generate_snapshot
import configparser
import time
from laboratory.custom import is_first_board_after_volume_consolidation
config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

class BuyOnDips:
    def __init__(self):
        self.download_start_time = config.get('DOWNLOAD', 'download_start_time')
        self.download_required = config.get('DOWNLOAD', 'download_required')

        self.backtest_start_time = config.get('BACKTEST', 'backtest_start_time')
        self.backtest_end_time = config.get('BACKTEST', 'backtest_end_time')
        self.initial_amount = config.getfloat('BACKTEST', 'initial_amount')
        self.commission_rate = config.getfloat('BACKTEST', 'commission_rate')
        self.min_commission = config.getfloat('BACKTEST', 'min_commission')
        self.tax_rate = config.getfloat('BACKTEST', 'tax_rate')

        self.positions = {} # 初始化持仓

    def run(self) -> bool:
        """
        策略运行
        Returns:
            bool: 是否成功
        """
        self.prepare()

        for trade_date in self.trade_calendar:
            self.before_open(trade_date)

            for minute_snapshot in self.minute_snapshots:
                self.on_minute(minute_snapshot)

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
        download_stock_history_data(self.global_stock_list, self.download_start_time, self.backtest_end_time, "1m", True)
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
        info(f"策略开盘前运行: {trade_date}")

        # 1. 获取自选股票列表（预买入）
        self.selected_stock_list = self._get_selected_stock_list(trade_date)
        info(f"获取自选股票列表（预买入）完成: {len(self.selected_stock_list)} 只股票")

        # 2. 获取持仓股票列表（预卖出）
        self.holding_stock_list = self._get_holding_stock_list(trade_date)
        info(f"获取持仓股票列表（预卖出）完成: {len(self.holding_stock_list)} 只股票")

        # 3. 缓存盘前指标数据（备用于盘中运行）
        self._set_cached(trade_date)
        info(f"缓存盘前数据（备用于盘中运行）完成")

        # 4. 获取当日股池的分时线行情数据，并模拟生成分时快照
        self.snapshots = self._simulate_minute_daily(trade_date)
        info(f"模拟生成分时行情快照数据完成")

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
            if is_first_board_after_volume_consolidation(stock_code, daily_bar):
                result.append(stock_code)
        info(f"获取自选股票列表（预买入）完成: {len(result)} 只股票")
        info(f"自选股票列表: {result}")



        return []

    def _get_holding_stock_list(self, trade_date: str) -> list:
        """
        获取持仓股票列表（预卖出）
        Args:
            trade_date: 交易日期
        Returns:
            list: 持仓股票列表
        """
        return []

    def _set_cached(self, trade_date: str) -> bool:
        """
        缓存盘前数据（备用于盘中运行）
        Args:
            trade_date: 交易日期
        Returns:
            bool: 是否成功
        """
        self.cached = {}
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
        daily_bars = get_daily_bars(stock_list, "1m", trade_date)
        snapshots = generate_snapshot(daily_bars)
        return snapshots
    
    def on_minute(self, snapshot: dict) -> bool:
        """
        策略盘中分时线运行
        Args:
            snapshot: 行情快照 {'time': time, 'snapshot': [{'stock_code': stock_code, 'bars': bars}]}
        Returns:
            bool: 是否成功
        """
        debug(f"策略盘中分时线运行: {snapshot}")

        for snp in snapshot['snapshot']:
            if snp['stock_code'] in self.selected_stock_list:
                signal = self._buy_signal(snp)
            elif snp['stock_code'] in self.holding_stock_list:
                signal = self._sell_signal(snp)
            if signal:
                self.trade(signal)

        return True

    def _buy_signal(self, snapshot: dict) -> dict:
        """
        买入信号
        Args:
            snapshot: 分时快照
        Returns:
            dict: 买入信号
        """
        return {}

    def _sell_signal(self, snapshot: dict) -> dict:
        """
        卖出信号
        Args:
            snapshot: 分时快照
        Returns:
            dict: 卖出信号
        """
        return {}

    def trade(self, signal: dict) -> bool:
        """
        交易
        Args:
            signal: 交易信号执行动作
        Returns:
            bool: 是否成功
        """
        return True