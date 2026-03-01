"""
模拟交易实现
"""
import configparser
from utils.logger import info, debug, error
from utils.backtest_config import is_verbose_mode
import pandas as pd
from datetime import datetime
from utils.util import time_str_to_datetime
import matplotlib.pyplot as plt
import os


class Broker:
    def __init__(self):
        """
        初始化模拟撮合 Broker，每次实例化时按当前 config.ini 加载资金与费用配置。
        """
        cfg = configparser.ConfigParser()
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, "config.ini")
        cfg.read(config_path, encoding="utf-8")

        # 账户初始资金及交易费用参数
        self.initial_amount = cfg.getfloat("BACKTEST", "initial_amount", fallback=100000.0)
        self.available_amount = self.initial_amount
        self.commission_rate = cfg.getfloat("BACKTEST", "commission_rate", fallback=0.0001)
        self.min_commission = cfg.getfloat("BACKTEST", "min_commission", fallback=5.0)
        self.tax_rate = cfg.getfloat("BACKTEST", "tax_rate", fallback=0.0005)

        # 仓位管理参数（单股最大买入控制）
        self.limit_vol_type = cfg.get("BACKTEST", "limit_vol_type", fallback="amount")
        self.max_vol_rate = cfg.getfloat("BACKTEST", "max_vol_rate", fallback=0.05)
        self.max_vol_amount = cfg.getfloat("BACKTEST", "max_vol_amount", fallback=100000.0)
        self.positions = {} # 持仓 {'stock_code': {'cost_price': cost_price, 'volume': volume, 'disabled_volume': disabled_volume}}
        self.transactions = [] # 交易记录 [{'stock_code': stock_code, 'price': price, 'volume': volume, 'action': action, 'cost_price': cost_price, 'time': time}]
        self.position_and_account_changes = [] # 持仓与账户信息变动记录 [{'trade_date': trade_date, 'stock_count': stock_count, 'stock_cost': stock_cost, 'stock_value': stock_value, 'available_amount': available_amount, 'total_assets': total_assets}]
        # 冗余模式：与 config [BACKTEST] verbose 一致，为 True 时买卖明细以 info 输出
        self.verbose = is_verbose_mode()

    def _log_trade(
        self,
        action: str,
        stock_code: str,
        price: float,
        volume: int,
        total_cost: float,
        commission: float,
        tax: float,
        time: str,
        desc: str,
    ) -> None:
        """
        根据冗余模式输出买卖明细：verbose 时用 info，否则用 debug。
        """
        time_dt = time_str_to_datetime(time)
        if action == "买入":
            msg = f"买入 {stock_code}，价格: {price}，数量: {volume}，金额: {round(total_cost, 2)}，佣金: {round(commission, 2)}，时间: {time_dt}，描述: {desc}"
        else:
            msg = f"卖出 {stock_code}，价格: {price}，数量: {volume}，金额: {round(total_cost, 2)}，佣金: {round(commission, 2)}，印花税: {round(tax, 2)}，时间: {time_dt}，描述: {desc}"
        if self.verbose:
            info(msg)
        else:
            debug(msg)

    def _log_trade_extra(self) -> None:
        """冗余模式下额外输出当前可用资金与持仓。"""
        # if self.verbose:
        #     info(f"当前可用资金: {self.available_amount}")
        #     info(f"当前持仓: {self.positions}")
        # else:
        #     debug(f"当前可用资金: {self.available_amount}")
        #     debug(f"当前持仓: {self.positions}")
        debug(f"当前可用资金: {self.available_amount}")
        debug(f"当前持仓: {self.positions}")

    def buy(self, signal: dict) -> bool:
        """
        买入
        Args:
            signal: 买入信号 {'action': 'buy', 'stock_code': stock_code, 'price': price, 'volume': volume, 'desc': desc}
        Returns:
            bool: 是否成功
        """
        stock_code = signal['stock_code']
        price = signal['price']
        volume = signal['volume']
        action = signal['action']
        time = signal['time']
        desc = signal['desc']
        minute_k_count = int(signal.get('minute_k_count', 0) or 0)
        # 计算买入金额
        total_cost = price * volume
        # 计算佣金
        commission = max(total_cost * self.commission_rate, self.min_commission)
        cost_all = total_cost + commission

        # 判断买入数量为0时，返回False
        if volume <= 0:
            info(f"买入数量为0，无法买入: {stock_code} 数量: {volume}, 时间: {time_str_to_datetime(time)}，描述: {desc}")
            return False
            
        # 判断是否可用资金不足，如果不足则返回False
        if self.available_amount < cost_all:
            info(f"资金不足，无法买入: {stock_code} 资金需求: {cost_all}, 可用: {self.available_amount}, 时间: {time_str_to_datetime(time)}，描述: {desc}")
            return False

        # 更新持仓
        self.set_position(stock_code, price, volume)
        # 更新可用资金
        self.available_amount -= cost_all
        # 记录交易
        self.record_transaction(
            stock_code=stock_code,
            price=price,
            volume=volume,
            action=action,
            cost_price=price,
            commission=commission,
            tax=0,
            time=time,
            desc=desc,
            minute_k_count=minute_k_count,
        )
        self._log_trade("买入", stock_code, price, volume, total_cost, commission, 0, time, desc)
        self._log_trade_extra()
        return True

    def sell(self, signal: dict) -> bool:
        """
        卖出
        Args:
            signal: 卖出信号 {'action': 'sell', 'stock_code': stock_code, 'price': price, 'volume': volume, 'desc': desc}
        Returns:
            bool: 是否成功
        """
        stock_code = signal['stock_code']
        price = signal['price']
        volume = signal['volume']
        action = signal['action']
        time = signal['time']
        desc = signal['desc']
        minute_k_count = int(signal.get('minute_k_count', 0) or 0)
        
        # 计算可用仓位
        available_volume = self.get_available_volume(stock_code)
        if available_volume < volume:
            info(f"可用仓位不足，无法卖出: {stock_code} 可用仓位: {available_volume}, 需求: {volume}, 时间: {time_str_to_datetime(time)}，描述: {desc}")
            return False
        # 计算卖出金额
        total_cost = price * volume
        # 计算佣金和印花税
        commission = max(total_cost * self.commission_rate, self.min_commission)
        tax = total_cost * self.tax_rate
        # 更新持仓
        self.set_position(stock_code, price, -volume)
        # 更新可用资金
        self.available_amount += total_cost - commission - tax
        # 记录交易
        self.record_transaction(
            stock_code=stock_code,
            price=price,
            volume=volume,
            action=action,
            cost_price=price,
            commission=commission,
            tax=tax,
            time=time,
            desc=desc,
            minute_k_count=minute_k_count,
        )
        self._log_trade("卖出", stock_code, price, volume, total_cost, commission, tax, time, desc)
        self._log_trade_extra()
        return True

    # 单股买入数量
    def get_buy_volume(self, price: float) -> int:
        """
        获取单股买入数量（根据仓位管理配置计算单股最大买入数量）
        Args:
            price: 买入价格
        Returns:
            int: 单股买入数量（100的整数倍，且不超过可用资金所能买入的数量）
        """
        # 获取仓位管理配置（来自当前实例的配置快照）
        limit_vol_type = self.limit_vol_type
        max_vol_rate = self.max_vol_rate
        max_vol_amount = self.max_vol_amount

        # 可能的最大买入资金（不能超过可用资金）
        max_affordable_volume = int(self.available_amount / price // 100 * 100)

        # 根据仓位管理配置计算单股最大买入数量，并向下取100的整数倍
        if limit_vol_type == 'ratio':
            total_amount = self.available_amount + self.get_position_value()
            calc_volume = int((total_amount * max_vol_rate) / price // 100 * 100)
        elif limit_vol_type == 'amount':
            calc_volume = int(max_vol_amount / price // 100 * 100)
        else:
            # 默认回退行为，不买入
            error(f"仓位管理配置错误，不买入: limit_vol_type: {limit_vol_type}, max_vol_rate: {max_vol_rate}, max_vol_amount: {max_vol_amount}")
            calc_volume = 0

        # 不能超过可用资金所能买入的数量
        buy_volume = min(calc_volume, max_affordable_volume)
        
        if buy_volume >= 100:
            return buy_volume
        else:
            return 0
        
    def get_position(self, stock_code: str) -> dict:
        """
        获取持仓信息
        Args:
            stock_code: 股票代码
        Returns:
            dict: 持仓 {'stock_code': stock_code, 'cost_price': cost_price, 'volume': volume, 'disabled_volume': disabled_volume}
        """
        return self.positions.get(stock_code, {})
    
    def get_available_volume(self, stock_code: str) -> int:
        """
        获取可用仓位
        Args:
            stock_code: 股票代码
        Returns:
            int: 可用仓位
        """
        return self.positions[stock_code]['volume'] - self.positions[stock_code]['disabled_volume']

    def set_position(self, stock_code: str, cost_price: float, volume: int) -> bool:
        """
        设置持仓
        Args:
            stock_code: 股票代码
            cost_price: 成本价格
            volume: 新增持仓股数（为0时不做变更）
        Returns:
            bool: 是否成功
        """
        if stock_code in self.positions:
            old_volume = self.positions[stock_code]['volume']
            old_cost_price = self.positions[stock_code]['cost_price']
            total_volume = old_volume + volume
            # 当新增持仓时，加权计算新成本价并锁定新增部分；当减少持仓时，不计算新成本价（仅变更volume）
            if volume > 0:
                new_cost_price = (old_cost_price * old_volume + cost_price * volume) / total_volume
                self.positions[stock_code]['cost_price'] = new_cost_price
                self.positions[stock_code]['disabled_volume'] = volume
            self.positions[stock_code]['volume'] = total_volume
        else:
            self.positions[stock_code] = {'cost_price': cost_price, 'volume': volume, 'disabled_volume': volume}
        return True

    def unlock_position(self) -> bool:
        """
        用于盘前解锁持仓，将所有被锁定的持仓解锁（disabled_volume置为0）
        Returns:
            bool: 是否成功
        """
        for stock_code in self.positions:
            self.positions[stock_code]['disabled_volume'] = 0
        return True

    def clean_position(self) -> bool:
        """
        用于盘前清除所有volume为0的持仓股票信息
        Returns:
            bool: 是否成功
        """
        for stock_code in list(self.positions.keys()):
            if self.positions.get(stock_code, {}).get('volume', 0) == 0:
                del self.positions[stock_code]
        return True

    # 盘后更新持仓信息
    def update_position(self, minute_snapshot: dict) -> bool:
        """
        盘后更新持仓信息（使用最后一个minute快照的close价格更新持仓最新价格）
        Args:
            minute_snapshot: 最后一个minute快照 {'minute': minute, 'snapshot': [{'stock_code': stock_code, 'bars': bars}]}
        Returns:
            bool: 是否成功
        """
        # 遍历持仓，使用最后一个minute快照的close价格更新持仓最新价格
        for stock_code in self.positions:
            stock_snapshot = next((item for item in minute_snapshot['snapshot'] if item['stock_code'] == stock_code), None)
            if stock_snapshot:
                bars = stock_snapshot['bars']
                if not bars.empty:
                    last_price = bars.iloc[-1]['close']
                    # last_price可能为NaN，此时不更新
                    if not pd.isna(last_price):
                        self.positions[stock_code]['last_price'] = last_price
                        debug(f"更新持仓最新价格: {stock_code}，价格: {last_price}")
        return True

    def get_position_cost(self) -> float:
        """
        获取持仓成本
        Returns:
            float: 持仓成本
        """
        return sum(pos.get('cost_price', 0) * pos.get('volume', 0) for pos in self.positions.values())

    def get_position_value(self) -> float:
        """
        获取持仓总价值
        Returns:
            float: 持仓价值
        """
        return sum(pos.get('last_price', 0) * pos.get('volume', 0) for pos in self.positions.values())

    def get_total_assets(self) -> float:
        """
        获取总资产
        Returns:
            float: 总资产
        """
        return self.available_amount + self.get_position_value()

    def get_total_profit_rate(self) -> float:
        """
        获取总盈利率
        Returns:
            float: 总盈利率
        """
        return (self.get_total_assets() / self.initial_amount - 1) * 100

    def record_transaction(
        self,
        stock_code: str,
        price: float,
        volume: int,
        action: str,
        cost_price: float,
        commission: float,
        tax: float,
        time: str,
        desc: str = "",
        minute_k_count: int = 0,
    ) -> bool:
        """
        记录每笔交易。

        Args:
            stock_code: 股票代码
            price: 价格
            volume: 股数
            action: 操作类型（buy 或 sell）
            cost_price: 成本价格
            commission: 佣金
            tax: 印花税
            time: 交易时间（原始时间字符串）
            desc: 描述/原因
            minute_k_count: 当日截至当前的分时 K 线数量（用于后续分析卖点）

        Returns:
            bool: 是否成功
        """
        self.transactions.append({
            'stock_code': stock_code,
            'price': price,
            'volume': volume,
            'action': action,
            'cost_price': cost_price,
            'commission': commission,
            'tax': tax,
            'time': time,
            'time_str': time_str_to_datetime(time),
            'desc': desc,
            'minute_k_count': minute_k_count,
        })
        return True
     
    def record_position_and_account_change(self, trade_date: str) -> bool:
        """
        记录持仓与账户信息变动记录（持仓数量、持仓成本、持仓价值、可用资金、总资产）
        Args:
            trade_date: 交易日期
        Returns:
            bool: 是否成功
        """
        # 获取个股持仓数量（volume>0的持仓股数）
        stock_count = len([pos for pos in self.positions.values() if pos['volume'] > 0])
        # 获取个股持仓成本
        stock_cost = sum(pos.get('cost_price', 0) * pos.get('volume', 0) for pos in self.positions.values() if pos.get('volume', 0) > 0)
        # 获取个股持仓价值
        stock_value = sum(pos.get('last_price', 0) * pos.get('volume', 0) for pos in self.positions.values() if pos.get('volume', 0) > 0)
        # 获取可用资金
        available_amount = self.available_amount
        # 获取总资产
        total_assets = self.get_total_assets()
        # 记录持仓与账户信息变动记录
        self.position_and_account_changes.append({
            'trade_date': trade_date,
            'stock_count': stock_count,
            'stock_cost': stock_cost,
            'stock_value': stock_value,
            'available_amount': available_amount,
            'total_assets': total_assets
        })
        return True

    # 获取个股建仓日期（最后一次买入日期）
    def get_build_date(self, stock_code: str) -> str:
        """
        获取个股建仓日期（最后一次买入日期）
        Args:
            stock_code: 股票代码
        Returns:
            str: 建仓日期，格式为'YYYYMMDD'，如果未找到建仓日期，则返回空字符串
        """
        # 首先检查该股票是否在持仓中，如果不在持仓中，则返回空字符串
        if stock_code not in self.positions:
            return ''

        # 从最近到最早，找到该股票最后一次买入的交易，直接取time_str前8位的数字返回，如果未找到建仓日期，则返回空字符串
        for transaction in reversed(self.transactions):
            if transaction.get('stock_code') == stock_code and transaction.get('action') == 'buy':
                time_str = str(transaction.get('time_str', ''))
                if len(time_str) >= 8:
                    return time_str.replace('-', '').replace(':', '').replace(' ', '')[:8]
        return ''

    def get_build_price(self, stock_code: str) -> float:
        """
        获取建仓价格
        Args:
            stock_code: 股票代码
        Returns:
            float: 建仓价格，未找到返回0.0
        """
        build_date = self.get_build_date(stock_code)
        if not build_date:
            return 0.0
        for transaction in reversed(self.transactions):
            if (transaction.get('stock_code') == stock_code 
                and transaction.get('action') == 'buy' 
                and str(transaction.get('time_str', '')).replace('-', '').replace(':', '').replace(' ', '')[:8] == build_date):
                return transaction.get('price', 0.0)
        return 0.0

    # 获取个股持仓成本
    def get_position_cost_price(self, stock_code: str) -> float:
        """
        获取个股持仓成本
        Args:
            stock_code: 股票代码
        Returns:
            float: 持仓成本，未找到返回0.0
        """
        return self.positions.get(stock_code, {}).get('cost_price', 0.0)


    def download_position_and_account_changes(self) -> bool:
        """
        下载持仓变动记录至excel文件 results/position_and_account_changes_YYYYMMDD_HHMMSS.xlsx
        Returns:
            bool: 是否成功
        """
        results_dir = "results"
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)
        
        # 检查数据是否为空，如果为空则提示并返回False
        if not self.position_and_account_changes:
            info("没有持仓变动记录需要导出")
            return False

        try:
            filename = f'{results_dir}/position_and_account_changes_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            df = pd.DataFrame(self.position_and_account_changes)
            if df.empty:
                info("持仓变动记录为空（DataFrame为空），未生成excel文件")
                return False
            df.to_excel(filename, index=False)
            info(f"下载持仓变动记录至excel文件完成- {filename}")
            return True
        except Exception as e:
            error(f"导出持仓变动记录失败: {e}")
            return False

    def download_transactions(self) -> bool:
        """
        下载交易记录与持仓变动记录至excel文件 results/results_YYYYMMDD_HHMMSS.xlsx 
        分别保存为两个sheet，sheet1为交易记录，sheet2为持仓变动记录
        Returns:
            bool: 是否成功
        """
        # 保证results目录存在
        results_dir = "results"
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)

        filename = f'{results_dir}/original_transactions_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        df_transactions = pd.DataFrame(self.transactions)
        df_position_and_account_changes = pd.DataFrame(self.position_and_account_changes)
        with pd.ExcelWriter(filename) as writer:
            df_transactions.to_excel(writer, sheet_name='交易记录', index=False)
            df_position_and_account_changes.to_excel(writer, sheet_name='持仓变动记录', index=False)
        info(f"下载交易记录与持仓变动记录至excel文件完成- {filename}")
        return True
