"""
模拟交易实现
"""
import configparser
from utils.logger import info, debug, error
import pandas as pd
from datetime import datetime
from utils.util import time_str_to_datetime
import matplotlib.pyplot as plt
config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

class Broker:
    def __init__(self):
        self.initial_amount = config.getfloat('BACKTEST', 'initial_amount')
        self.available_amount = self.initial_amount
        self.commission_rate = config.getfloat('BACKTEST', 'commission_rate')
        self.min_commission = config.getfloat('BACKTEST', 'min_commission')
        self.tax_rate = config.getfloat('BACKTEST', 'tax_rate')
        self.positions = {} # 持仓 {'stock_code': {'cost_price': cost_price, 'volume': volume, 'disabled_volume': disabled_volume}}
        self.transactions = [] # 交易记录 [{'stock_code': stock_code, 'price': price, 'volume': volume, 'action': action, 'cost_price': cost_price, 'time': time}]
        self.position_and_account_changes = [] # 持仓与账户信息变动记录 [{'trade_date': trade_date, 'stock_count': stock_count, 'stock_cost': stock_cost, 'stock_value': stock_value, 'available_amount': available_amount, 'total_assets': total_assets}]

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
        # 计算买入金额
        total_cost = price * volume
        # 计算佣金
        commission = max(total_cost * self.commission_rate, self.min_commission)
        cost_all = total_cost + commission
        # 判断是否可用资金不足，如果不足则返回False
        if self.available_amount < cost_all:
            info(f"资金不足，无法买入: {stock_code} 资金需求: {cost_all}, 可用: {self.available_amount}, 时间: {time_str_to_datetime(time)}，描述: {desc}")
            return False
        # 更新持仓
        self.set_position(stock_code, price, volume)
        # 更新可用资金
        self.available_amount -= cost_all
        # 记录交易
        self.record_transaction(stock_code, price, volume, action, price, commission, 0, time)
        info(f"买入 {stock_code}，价格: {price}，数量: {volume}，金额: {total_cost}，佣金: {commission}，时间: {time_str_to_datetime(time)}，描述: {desc}")
        debug(f"当前可用资金: {self.available_amount}")
        debug(f"当前持仓: {self.positions}")
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
        self.record_transaction(stock_code, price, volume, action, price, commission, tax, time)
        info(f"卖出 {stock_code}，价格: {price}，数量: {volume}，金额: {total_cost}，佣金: {commission}，印花税: {tax}，时间: {time_str_to_datetime(time)}，描述: {desc}")
        debug(f"当前可用资金: {self.available_amount}")
        debug(f"当前持仓: {self.positions}")
        return True

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
                    self.positions[stock_code]['last_price'] = bars.iloc[-1]['close']
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
        获取持仓价值
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

    def record_transaction(self, stock_code: str, price: float, volume: int, action: str, cost_price: float, commission: float, tax: float, time: str) -> bool:
        """
        记录每笔交易
        Args:
            stock_code: 股票代码
            price: 价格
            volume: 股数
            action: 操作类型（buy或sell）
            cost_price: 成本价格
            commission: 佣金
            tax: 印花税
            time: 交易时间
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
            'time_str': time_str_to_datetime(time)
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

    # 下载交易记录至csv文件
    def download_transactions(self) -> bool:
        """
        下载交易记录与持仓变动记录至csv文件 results/results_YYYYMMDD_HHMMSS.csv 
        分别保存为两个sheet，sheet1为交易记录，sheet2为持仓变动记录
        Returns:
            bool: 是否成功
        """
        df_transactions = pd.DataFrame(self.transactions)
        df_position_and_account_changes = pd.DataFrame(self.position_and_account_changes)
        with pd.ExcelWriter(f'results/results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx') as writer:
            df_transactions.to_excel(writer, sheet_name='交易记录', index=False)
            df_position_and_account_changes.to_excel(writer, sheet_name='持仓变动记录', index=False)
        info(f"下载交易记录与持仓变动记录至csv文件完成- results/results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx")
        return True

    # 分析结果
    def analyze_result(self) -> bool:
        """
        分析结果，包括真正的最大回撤计算，并增加最大持仓股票数与平均持仓天数计算
        Returns:
            bool: 是否成功
        """
        try:
            total_position_value = self.get_position_value()
            total_assets = self.get_total_assets()
            total_return = self.get_total_profit_rate()

            # 1. 统计交易次数及成本
            total_trades = len(self.transactions)
            total_commission = sum(t.get('commission', 0) for t in self.transactions)
            total_tax = sum(t.get('tax', 0) for t in self.transactions)
            total_costs = total_commission + total_tax
            stock_count_list = [x['stock_count'] for x in self.position_and_account_changes] if self.position_and_account_changes else []
            max_position_count = max(stock_count_list) if stock_count_list else 0

            # 2. 个股闭环盈亏统计
            df = pd.DataFrame(self.transactions)
            stock_perf = {}
            if not df.empty:
                for code, trades in df.groupby('stock_code'):
                    buys = trades[trades['action'] == 'buy']
                    sells = trades[trades['action'] == 'sell']
                    if not buys.empty and not sells.empty:
                        buy_amt = (buys['price'] * buys['volume']).sum()
                        buy_comm = buys['commission'].sum() if 'commission' in buys else 0
                        buy_cost = buy_amt + buy_comm
                        sell_amt = (sells['price'] * sells['volume']).sum()
                        sell_comm = sells['commission'].sum() if 'commission' in sells else 0
                        sell_tax = sells['tax'].sum() if 'tax' in sells else 0
                        sell_income = sell_amt - sell_comm - sell_tax
                        pl = sell_income - buy_cost
                        rr = (pl / buy_cost) * 100 if buy_cost != 0 else 0
                        stock_perf[code] = dict(return_rate=rr, buy_cost=buy_cost, sell_income=sell_income, profit_loss=pl)

            completed = list(stock_perf.values())
            total_completed = len(completed)
            win_rates = [x['return_rate'] for x in completed if x['return_rate'] > 0]
            loss_rates = [x['return_rate'] for x in completed if x['return_rate'] < 0]
            win_rate = (len(win_rates) / total_completed * 100) if total_completed else 0
            avg_profit_rate = sum(win_rates) / len(win_rates) if win_rates else 0
            avg_loss_rate = sum(loss_rates) / len(loss_rates) if loss_rates else 0

            # 3. 计算历史资产曲线最大回撤（真实最大回撤）
            max_assets = -float('inf')
            max_drawdown = 0.0
            # 获取资产曲线（按日期排序）
            if self.position_and_account_changes:
                df_pac = pd.DataFrame(self.position_and_account_changes)
                df_pac = df_pac.sort_values('trade_date')
                asset_curve = df_pac['total_assets'].tolist()
                if asset_curve:
                    peak = asset_curve[0]
                    max_dd = 0.0
                    for v in asset_curve:
                        if v > peak:
                            peak = v
                        dd = (peak - v) / peak if peak != 0 else 0
                        if dd > max_dd:
                            max_dd = dd
                    max_drawdown = max_dd * 100
                else:
                    max_drawdown = 0.0
            else:
                max_drawdown = 0.0

            # 4. 输出分析
            info("=" * 100)
            info("回测分析结果")
            info("=" * 100)
            info(f"初始资金: {self.initial_amount:,.2f} 元")
            info(f"当前可用资金: {self.available_amount:,.2f} 元")
            info(f"持仓价值(成本价估算): {total_position_value:,.2f} 元")
            info(f"总资产: {total_assets:,.2f} 元")
            info(f"总盈利: {total_return:.2f}%")
            info(f"总交易次数: {total_trades}")
            info(f"完成交易股票数: {total_completed}")
            info(f"胜率: {win_rate:.2f}%")
            info(f"平均盈利率: {avg_profit_rate:.2f}%")
            info(f"平均亏损率: {avg_loss_rate:.2f}%")
            info(f"最大回撤: {max_drawdown:.2f}%")
            info(f"最大持仓股票数: {max_position_count}")
            info(f"总手续费: {total_commission:,.2f} 元")
            info(f"总印花税: {total_tax:,.2f} 元")
            info(f"总交易成本: {total_costs:,.2f} 元")
            info("=" * 100)

            if stock_perf:
                info("各股票表现详情:")
                for code, v in stock_perf.items():
                    stat = "盈利" if v['return_rate'] > 0 else "亏损"
                    info(f"  {code}: {v['return_rate']:.2f}% ({stat})")

            return True
        except Exception as e:
            error(f"分析结果时发生错误: {e}")
            return False