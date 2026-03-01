"""
策略基类模块
提供策略开发所需的基础框架和通用功能
"""
import os
import time
import configparser
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional

import pandas as pd
from tqdm import tqdm

from utils.data import (
    get_daily_bars,
    get_daily_bars_from_cache,
    get_stock_list_in_main_board,
    get_trade_calendar,
)
from utils.logger import debug, info
from utils.util import add_num_date_days, generate_minute_snapshot, get_elapsed_time_str
from utils.broker import Broker
from laboratory.analyze import analyze_account_changes, analyze_buy_and_sell_record


class BaseStrategy(ABC):
    """
    策略基类
    提供策略回测的基础框架，子类需要实现选股、信号生成等核心逻辑
    """
    
    def __init__(self):
        """
        初始化策略：按当前 config.ini 读取回测配置，并构造撮合 Broker。
        """
        self.start_time = time.time()
        # 回测中止标记，用于外部请求优雅停止回测
        self._stop_requested: bool = False
        # 回测进度回调（由外部注入，例如 Web 服务），签名：callback(stage:str, current:int, total:int) -> None
        self._progress_callback: Optional[Callable[[str, int, int], None]] = None

        # 每次实例化策略时重新读取配置，避免长生命周期进程中使用旧配置
        cfg = configparser.ConfigParser()
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, "config.ini")
        cfg.read(config_path, encoding="utf-8")

        self.backtest_start_time = cfg.get("BACKTEST", "backtest_start_time", fallback="")
        self.backtest_end_time = cfg.get("BACKTEST", "backtest_end_time", fallback="")
        # 冗余日志开关：True=冗余模式，False=简约模式
        try:
            self.verbose = cfg.getboolean("BACKTEST", "verbose", fallback=False)
        except (TypeError, ValueError):
            self.verbose = False
        self.broker = Broker()
        # 选股是否使用多线程（False 时单线程顺序选股，便于开发调试）
        try:
            self._batch_stock_selection_use_threads = cfg.getboolean(
                "BACKTEST", "batch_stock_selection_use_threads", fallback=True
            )
        except (TypeError, ValueError):
            self._batch_stock_selection_use_threads = True
        # 预选股线程数（仅多线程模式下生效，0=自动）
        try:
            self._batch_stock_selection_threads = int(
                cfg.get("BACKTEST", "batch_stock_selection_threads", fallback="0"),
            )
        except (TypeError, ValueError):
            self._batch_stock_selection_threads = 0
        
        # 交易日历和股票池（在prepare中初始化）
        self.trade_calendar = []
        self.global_stock_list = []
        
        # 每日运行时的数据（在before_open中初始化）
        self.selected_stock_list = []  # 自选股票列表（预买入）
        self.holding_stock_list = []   # 持仓股票列表（预卖出）
        self.cached = {}               # 缓存盘前数据
        self.minute_snapshots = []     # 分时快照数据
        # 多线程预选股结果：{ trade_date: [stock_codes] }，由 prepare 中批量选股填充
        self._selected_stock_by_date: Dict[str, List[str]] = {}
        # 日线全量缓存，选股前一次性加载，多线程选股时只读此内存，不访问 DuckDB
        self._daily_bars_cache: Optional[Dict] = None

    def _is_verbose_mode(self) -> bool:
        """
        判断当前是否为冗余(verbose)模式。

        Returns:
            bool: True=冗余(verbose)，False=简约(simple)。
        """
        return bool(getattr(self, "verbose", False))

    def set_progress_callback(self, callback: Optional[Callable[[str, int, int], None]]) -> None:
        """
        设置回测进度回调函数。

        该回调通常由外部环境（如 Web 服务）在实例化策略后注入，用于在每日
        回测循环中上报当前进度，从而在前端展示回测进度。

        Args:
            callback: 进度回调函数，入参为 (stage, current, total)，
                      stage 为阶段标识（如 "selection" 或 "backtest"）；
                      current 表示已完成交易日数量，total 表示总交易日数量。
        """
        self._progress_callback = callback

    def _tqdm_disable(self) -> bool:
        """
        根据运行模式决定是否禁用 tqdm 进度条。

        - verbose = False: 显示进度条（简约模式）
        - verbose = True : 不显示进度条（冗余模式，避免与大量日志混杂）

        Returns:
            bool: True=禁用进度条，False=显示进度条
        """
        return self._is_verbose_mode()

    def _info_verbose(self, message: str) -> None:
        """
        仅在冗余(verbose)模式输出 info 日志。

        Args:
            message: 日志内容
        """
        if self._is_verbose_mode():
            info(message)

    def request_stop(self) -> None:
        """
        请求中止当前回测。

        外部调用该方法（例如 Web 服务）时，不会立刻强制退出，
        而是在当前交易日循环安全点检测到标记后优雅结束回测。
        """
        self._stop_requested = True
        self._info_verbose("收到中止回测请求，将在当前交易日结束后停止。")

    def _is_stop_requested(self) -> bool:
        """
        检查是否已收到中止回测请求。

        Returns:
            bool: True 表示需要尽快结束回测。
        """
        return bool(getattr(self, "_stop_requested", False))

    def run(self) -> bool:
        """
        策略运行主流程。

        该方法会依次执行：
        1. `prepare` 预处理；
        2. 按交易日历逐日回测（支持外部中止与进度回调）；
        3. `end_of_backtest` 回测收尾与结果分析。

        Returns:
            bool: 是否成功。
        """
        self.prepare()
        # 遍历交易日历，逐日运行（最后一天不运行）
        trade_days = self.trade_calendar[:-1]
        total_days = len(trade_days)
        for idx, trade_date in enumerate(
            tqdm(trade_days, desc="回测进度", unit="日", disable=self._tqdm_disable()),
            start=1,
        ):
            # 支持外部中止请求：在每日循环入口检查标记
            if self._is_stop_requested():
                info(f"检测到中止回测请求，提前结束回测，最后交易日: {trade_date}")
                break
            # 向外部环境上报回测进度（如已注入回调）
            if self._progress_callback is not None:
                try:
                    self._progress_callback("backtest", idx, total_days)
                except Exception:
                    # 进度回调失败不影响主流程，忽略异常即可
                    pass
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
        
        # 3. 批量预选股并写入 _selected_stock_by_date
        self._run_batch_stock_selection()
        
        return True

    def _run_batch_stock_selection(self) -> None:
        """
        对所有交易日执行选股，结果写入 self._selected_stock_by_date。
        选股前一次性加载日线全量到内存；是否多线程由配置 batch_stock_selection_use_threads 控制，
        True 时多线程选股（线程数由 batch_stock_selection_threads 决定，0 为自动），
        False 时单线程顺序选股（便于开发调试）。
        """
        trade_days = self.trade_calendar[:-1]
        if not trade_days:
            return
        self._selected_stock_by_date.clear()
        # 选股前一次性加载日线全量到内存（主线程、单次 DuckDB 访问）
        info("加载日线全量数据到内存...")
        self._daily_bars_cache = get_daily_bars(
            self.global_stock_list,
            period="1d",
            start_time="",
            end_time=self.backtest_end_time,
            count=-1,
        )
        info("日线全量数据加载完成")
        total_days = len(trade_days)

        if self._batch_stock_selection_use_threads:
            self._run_batch_stock_selection_multi_thread(trade_days, total_days)
        else:
            self._run_batch_stock_selection_single_thread(trade_days, total_days)
        info("选股完成")

    def _run_batch_stock_selection_single_thread(
        self, trade_days: List[str], total_days: int
    ) -> None:
        """
        单线程顺序选股，便于开发调试（无多线程干扰，异常堆栈清晰）。
        """
        info(f"开始单线程选股: 共 {total_days} 个交易日")
        for completed, trade_date in enumerate(
            tqdm(trade_days, desc="选股进度", unit="日", disable=self._tqdm_disable()),
            start=1,
        ):
            try:
                self._selected_stock_by_date[trade_date] = self.get_selected_stock_list(
                    trade_date
                )
            except Exception as e:
                debug(f"选股异常 trade_date={trade_date}: {e}")
                self._selected_stock_by_date[trade_date] = []
            if self._progress_callback is not None:
                try:
                    self._progress_callback("selection", completed, total_days)
                except Exception:
                    pass

    def _run_batch_stock_selection_multi_thread(
        self, trade_days: List[str], total_days: int
    ) -> None:
        """
        多线程选股，线程数由配置 batch_stock_selection_threads 决定，0 为自动。
        """
        if self._batch_stock_selection_threads > 0:
            max_workers = min(self._batch_stock_selection_threads, len(trade_days))
        else:
            max_workers = min((os.cpu_count() or 4), len(trade_days))
        info(f"开始多线程选股: 共 {total_days} 个交易日, 线程数 {max_workers}")
        with tqdm(
            total=total_days, desc="选股进度", unit="日", disable=self._tqdm_disable()
        ) as pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_date = {
                    executor.submit(self.get_selected_stock_list, d): d
                    for d in trade_days
                }
                completed = 0
                for future in as_completed(future_to_date):
                    trade_date = future_to_date[future]
                    try:
                        self._selected_stock_by_date[trade_date] = future.result()
                    except Exception as e:
                        debug(f"选股异常 trade_date={trade_date}: {e}")
                        self._selected_stock_by_date[trade_date] = []
                    pbar.update(1)
                    completed += 1
                    if self._progress_callback is not None:
                        try:
                            self._progress_callback("selection", completed, total_days)
                        except Exception:
                            pass

    def get_daily_bars_for_selection(self, trade_date: str, count: int) -> dict:
        """
        选股用日线数据：有预选股缓存时从内存切片，否则调 get_daily_bars。子类选股时应使用本方法。
        Args:
            trade_date: 截止交易日期（含）
            count: 从该日往前取条数
        Returns:
            dict: {stock_code: DataFrame}，与 get_daily_bars(..., end_time=trade_date, count=count) 一致
        """
        if self._daily_bars_cache is not None:
            return get_daily_bars_from_cache(
                self._daily_bars_cache,
                self.global_stock_list,
                trade_date,
                count,
            )
        return get_daily_bars(
            self.global_stock_list,
            period="1d",
            end_time=trade_date,
            count=count,
        )

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
        self._info_verbose(f"策略开盘前运行: 【{add_num_date_days(trade_date, 1, self.trade_calendar)}】")
        
        # 资产概览
        self._info_verbose(
            f"可用资金: {self.broker.available_amount:,.2f} 元，持仓价值: {self.broker.get_position_value():,.2f} 元，"
            f"总资产: {self.broker.get_total_assets():,.2f} 元, 总盈利率: {self.broker.get_total_profit_rate():,.2f}%"
        )
        
        # 盘前清理：清除volume为0的持仓股票信息、解锁昨日所有被锁定的持仓
        self.broker.clean_position()
        self.broker.unlock_position()
        
        # 1. 获取持仓股票列表（预卖出）
        self.holding_stock_list = self._get_holding_stock_list()
        
        # 2. 获取自选股票列表（预买入），优先使用预选股缓存，再过滤掉已持仓
        if self._selected_stock_by_date and trade_date in self._selected_stock_by_date:
            self.selected_stock_list = self._selected_stock_by_date[trade_date]
        else:
            self.selected_stock_list = self.get_selected_stock_list(trade_date)
        self.selected_stock_list = [stock_code for stock_code in self.selected_stock_list if stock_code not in self.holding_stock_list]
        self._info_verbose(f"自选股票列表（预买入）: {self.selected_stock_list}")
        
        if not self.selected_stock_list and not self.holding_stock_list:
            self._info_verbose("没有自选股票和持仓股票，跳过策略开盘前运行")
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
        self._info_verbose(f"获取持仓股票列表（预卖出）完成: {len(result)} 只股票")
        self._info_verbose(f"持仓股票列表: {result}")
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
            self._info_verbose("没有分时快照数据，跳过盘后更新持仓信息")
        
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
