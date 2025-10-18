"""
买入在低点策略实现
"""
from asyncio.windows_events import NULL
from doctest import debug
from utils.data import get_stock_list_in_main_board, download_stock_history_data
from utils.data import get_trade_calendar
from utils.data import get_daily_bars
from utils.logger import info, debug
from utils.util import generate_snapshot


class BuyOnDips:
    def __init__(self, backtest_start_time: str, backtest_end_time: str, download_start_time: str):
        self.backtest_start_time = backtest_start_time
        self.backtest_end_time = backtest_end_time
        self.download_start_time = download_start_time
        self.positions = {}

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
        1. 获取大盘股票池并下载历史数据
        2. 获取交易日期列表
        Returns:
            bool: 是否准备成功
        """
        # 1. 获取大盘股票池并下载历史数据
        stock_list = get_stock_list_in_main_board()
        download_stock_history_data(stock_list, self.download_start_time, "1d", True)
        info(f"下载股票历史数据完成: {len(stock_list)} 只股票，开始时间: {self.download_start_time}")

        # 2. 获取交易日期列表
        self.trade_calendar = get_trade_calendar(self.backtest_start_time, self.backtest_end_time)
        info(f"获取交易日期列表完成: {len(self.trade_calendar)} 天")

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