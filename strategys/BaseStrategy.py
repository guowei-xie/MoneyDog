"""
策略基类模块
提供策略开发所需的基础框架和通用功能
"""
import time
import configparser
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

import pandas as pd
from tqdm import tqdm

from utils.data import get_stock_list_in_main_board, get_trade_calendar
from utils.logger import info, debug
from utils.util import generate_minute_snapshot, get_elapsed_time_str, add_num_date_days
from utils.broker import Broker
from laboratory.analyze import analyze_buy_and_sell_record, analyze_account_changes


class BaseStrategy(ABC):
    """
    策略基类
    提供策略回测的基础框架，子类需要实现选股、信号生成等核心逻辑
    """
    
    def __init__(self):
        """
        初始化策略
        """
        self.start_time = time.time()

        # 每次实例化策略时重新读取配置，避免长生命周期进程中使用旧配置
        cfg = configparser.ConfigParser()
        cfg.read('config.ini', encoding='utf-8')
        self.backtest_start_time = cfg.get('BACKTEST', 'backtest_start_time')
        self.backtest_end_time = cfg.get('BACKTEST', 'backtest_end_time')
        self.broker = Broker()
        
        # 交易日历和股票池（在prepare中初始化）
        self.trade_calendar = []
        self.global_stock_list = []
        
        # 每日运行时的数据（在before_open中初始化）
        self.selected_stock_list = []  # 自选股票列表（预买入）
        self.holding_stock_list = []   # 持仓股票列表（预卖出）
        self.cached = {}               # 缓存盘前数据
        self.minute_snapshots = []     # 分时快照数据

    def run(self) -> bool:
        """
        策略运行主流程
        Returns:
            bool: 是否成功
        """
        self.prepare()
        # 遍历交易日历，逐日运行（最后一天不运行）
        trade_days = self.trade_calendar[:-1]
        for trade_date in tqdm(trade_days, desc="回测进度", unit="日"):
            proceed = self.before_open(trade_date)
            if proceed:
                for minute_snapshot in self.minute_snapshots:
                    self.on_minute(minute_snapshot)
            self.after_close(trade_date)
            debug("=" * 100)
        self.end_of_backtest()
        return True

    def prepare(self) -> bool:
        """
        准备策略运行环境
        1. 获取交易日期列表
        2. 获取股票池
        Returns:
            bool: 是否准备成功
        """
        # 1. 获取交易日期列表
        self.trade_calendar = get_trade_calendar(self.backtest_start_time, self.backtest_end_time)
        info(f"获取交易日期列表完成: {len(self.trade_calendar)} 天")
        
        # 2. 获取股票池（默认使用主板股票池，子类可重写_get_stock_list方法）
        self.global_stock_list = self._get_stock_list()
        info(f"获取股票池完成: {len(self.global_stock_list)} 只股票")
        
        return True

    def _get_stock_list(self) -> List[str]:
        """
        获取股票池（默认使用主板股票池）
        子类可重写此方法以使用不同的股票池
        Returns:
            List[str]: 股票代码列表
        """
        return get_stock_list_in_main_board()

    def before_open(self, trade_date: str) -> bool:
        """
        策略开盘前运行
        Args:
            trade_date: 交易日期（如 '20250101'）
        Returns:
            bool: 是否继续运行当日策略
        """
        debug(f"策略开盘前运行: 【{add_num_date_days(trade_date, 1, self.trade_calendar)}】")
        
        # 资产概览
        debug(f"可用资金: {self.broker.available_amount:,.2f} 元，持仓价值: {self.broker.get_position_value():,.2f} 元，总资产: {self.broker.get_total_assets():,.2f} 元, 总盈利率: {self.broker.get_total_profit_rate():,.2f}%")
        
        # 盘前清理：清除volume为0的持仓股票信息、解锁昨日所有被锁定的持仓
        self.broker.clean_position()
        self.broker.unlock_position()
        
        # 1. 获取持仓股票列表（预卖出）
        self.holding_stock_list = self._get_holding_stock_list()
        
        # 2. 获取自选股票列表（预买入），过滤掉已经持仓的股票
        self.selected_stock_list = self.get_selected_stock_list(trade_date)
        self.selected_stock_list = [stock_code for stock_code in self.selected_stock_list if stock_code not in self.holding_stock_list]
        debug(f"自选股票列表（预买入）: {self.selected_stock_list}")
        
        if not self.selected_stock_list and not self.holding_stock_list:
            debug(f"没有自选股票和持仓股票，跳过策略开盘前运行")
            self.minute_snapshots = []
            return False
        
        # 3. 缓存盘前指标数据（备用于盘中运行）
        self.set_cached(trade_date)
        
        # 4. 获取当日分时线数据，并模拟分时快照数据
        self.minute_snapshots = self._simulate_minute_daily(add_num_date_days(trade_date, 1, self.trade_calendar))
        
        return True

    def _get_holding_stock_list(self) -> List[str]:
        """
        获取持仓股票列表（预卖出）
        Returns:
            List[str]: 持仓股票代码列表
        """
        positions = self.broker.positions
        result = []
        # 检查每个持仓，volume大于0的才是实际持仓
        for stock_code, position in positions.items():
            if position.get('volume', 0) > 0:
                result.append(stock_code)
        debug(f"获取持仓股票列表（预卖出）完成: {len(result)} 只股票")
        debug(f"持仓股票列表: {result}")
        return result

    @abstractmethod
    def get_selected_stock_list(self, trade_date: str) -> List[str]:
        """
        获取自选股票列表（预买入）
        子类必须实现此方法
        Args:
            trade_date: 交易日期
        Returns:
            List[str]: 自选股票代码列表
        """
        pass

    @abstractmethod
    def set_cached(self, trade_date: str) -> bool:
        """
        缓存盘前数据（备用于盘中运行）
        子类必须实现此方法
        Args:
            trade_date: 交易日期
        Returns:
            bool: 是否成功
        """
        pass

    def _simulate_minute_daily(self, trade_date: str) -> List[Dict]:
        """
        模拟分时快照数据（每分钟累积数据）
        Args:
            trade_date: 交易日期
        Returns:
            List[Dict]: 各股票各分钟的快照数据 [{'minute': minute, 'snapshot': [{'stock_code': stock_code, 'bars': bars}]}]
        """
        from utils.data import get_daily_bars
        stock_list = self.selected_stock_list + self.holding_stock_list
        daily_bars = get_daily_bars(stock_list, "1m", trade_date, trade_date, count=-1)
        snapshots = generate_minute_snapshot(daily_bars)
        return snapshots

    def on_minute(self, snapshot: Dict) -> bool:
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
            
            # 策略盘中分时线运行开始时运行自定义方法
            self.on_minute_start(stock_code, bars)

            # 根据股票是否在自选或持仓列表，调用相应的信号方法
            if stock_code in self.selected_stock_list:
                signal = self.buy_signal(stock_code, bars)
            elif stock_code in self.holding_stock_list:
                signal = self.sell_signal(stock_code, bars)
            else:
                continue
            
            # 如果有信号，执行交易
            if signal is not None:
                self.trade(signal)

            # 策略盘中分时线运行结束后运行自定义方法
            self.on_minute_end(stock_code, bars)
        return True
    
    def on_minute_end(self, stock_code: str, bars: pd.DataFrame):
        """
        策略盘中分时线运行结束后运行
        """
        pass

    def on_minute_start(self, stock_code: str, bars: pd.DataFrame):
        """
        策略盘中分时线运行开始时运行
        """
        pass

    @abstractmethod
    def buy_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        买入信号生成。

        子类必须实现此方法，并返回统一格式的信号字典。

        Args:
            stock_code: 股票代码
            bars: 分时K线快照（DataFrame）

        Returns:
            Optional[Dict]:
                买入信号:
                {
                    'action': 'buy',
                    'stock_code': stock_code,
                    'price': price,
                    'volume': volume,
                    'time': time,
                    'desc': desc,
                    'minute_k_count': int  # 当日截至当前的分时K线数量
                }
                无信号返回 None。
        """
        pass
        
    @abstractmethod
    def sell_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        卖出信号生成。

        子类必须实现此方法，并返回统一格式的信号字典。

        Args:
            stock_code: 股票代码
            bars: 分时K线快照（DataFrame）

        Returns:
            Optional[Dict]:
                卖出信号:
                {
                    'action': 'sell',
                    'stock_code': stock_code,
                    'price': price,
                    'volume': volume,
                    'time': time,
                    'desc': desc,
                    'minute_k_count': int  # 当日截至当前的分时K线数量
                }
                无信号返回 None。
        """
        pass

    def trade(self, signal: Dict) -> bool:
        """
        执行交易
        Args:
            signal: 交易信号:
                {
                    'action': 'buy'/'sell',
                    'stock_code': stock_code,
                    'price': price,
                    'volume': volume,
                    'time': time,
                    'desc': desc,
                    'minute_k_count': int  # 当日截至当前的分时K线数量
                }
        Returns:
            bool: 是否成功
        """
        if signal['action'] == 'sell':
            self.broker.sell(signal)
        elif signal['action'] == 'buy':
            self.broker.buy(signal)
        return True

    def after_close(self, trade_date: str) -> bool:
        """
        每日收盘后运行
        Args:
            trade_date: 交易日期
        Returns:
            bool: 是否成功
        """
        # 使用最后一个分时快照更新持仓信息
        if self.minute_snapshots:
            minute_snapshot = self.minute_snapshots[-1]
            self.broker.update_position(minute_snapshot)
        else:
            debug(f"没有分时快照数据，跳过盘后更新持仓信息")
        
        # 记录持仓和账户变化
        self.broker.record_position_and_account_change(trade_date)
        
        return True

    def end_of_backtest(self) -> bool:
        """
        回测结束
        Returns:
            bool: 是否成功
        """
        # 下载交易记录和账户变化数据
        self.broker.download_transactions()
        self.broker.download_position_and_account_changes()
        
        # 先分析交易记录，再分析账户变动（传入交易结果以绘制按买入日个股盈利率图）
        tx_result = analyze_buy_and_sell_record(transactions=self.broker.transactions)
        analyze_account_changes(
            position_and_account_changes=self.broker.position_and_account_changes,
            transactions_df=tx_result,
        )
        
        info(f"回测结束，运行耗时: {get_elapsed_time_str(self.start_time)}")
        return True
