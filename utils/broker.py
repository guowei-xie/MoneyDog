"""
模拟交易实现
"""
import configparser
from utils.logger import info, debug, error
import pandas as pd
from datetime import datetime
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

    def buy(self, signal: dict) -> bool:
        """
        买入
        Args:
            signal: 买入信号 {'action': 'buy', 'stock_code': stock_code, 'price': price, 'volume': volume}
        Returns:
            bool: 是否成功
        """
        stock_code = signal['stock_code']
        price = signal['price']
        volume = signal['volume']
        action = signal['action']
        time = signal['time']

        # 计算买入金额
        total_cost = price * volume
        # 计算佣金
        commission = max(total_cost * self.commission_rate, self.min_commission)
        cost_all = total_cost + commission
        # 判断是否可用资金不足，如果不足则返回False
        if self.available_amount < cost_all:
            info(f"资金不足，无法买入: {stock_code} 资金需求: {cost_all}, 可用: {self.available_amount}, 时间: {time}")
            return False
        # 更新持仓
        self.set_position(stock_code, price, volume)
        # 更新可用资金
        self.available_amount -= cost_all
        # 记录交易
        self.record_transaction(stock_code, price, volume, action, price, commission, 0, time)
        info(f"买入 {stock_code}，价格: {price}，数量: {volume}，金额: {total_cost}，佣金: {commission}，时间: {time}")
        debug(f"当前可用资金: {self.available_amount}")
        debug(f"当前持仓: {self.positions}")
        return True

    def sell(self, signal: dict) -> bool:
        """
        卖出
        Args:
            signal: 卖出信号 {'action': 'sell', 'stock_code': stock_code, 'price': price, 'volume': volume}
        Returns:
            bool: 是否成功
        """
        stock_code = signal['stock_code']
        price = signal['price']
        volume = signal['volume']
        action = signal['action']
        time = signal['time']
        
        # 计算可用仓位
        available_volume = self.get_available_volume(stock_code)
        if available_volume < volume:
            info(f"可用仓位不足，无法卖出: {stock_code} 可用仓位: {available_volume}, 需求: {volume}, 时间: {time}")
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
        info(f"卖出 {stock_code}，价格: {price}，数量: {volume}，金额: {total_cost}，佣金: {commission}，印花税: {tax}，时间: {time}")
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

    def get_position_cost(self) -> float:
        """
        获取持仓成本
        Returns:
            float: 持仓成本
        """
        return sum(pos.get('cost_price', 0) * pos.get('volume', 0) for pos in self.positions.values())

    def get_total_assets(self) -> float:
        """
        获取总资产
        Returns:
            float: 总资产
        """
        return self.available_amount + self.get_position_cost()

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
            'time': time
        })
        return True

    # 下载交易记录至csv文件
    def download_transactions(self) -> bool:
        """
        下载交易记录至csv文件 results/transactions_YYYYMMDD_HHMMSS.csv
        Returns:
            bool: 是否成功
        """
        df = pd.DataFrame(self.transactions)
        df.to_csv(f'results/transactions_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv', index=False)
        info(f"下载交易记录至csv文件完成- results/transactions_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv")
        return True

    # 分析结果
    def analyze_result(self) -> bool:
        """
        分析结果
        Returns:
            bool: 是否成功
        """
        try:
            # 1. 计算总资产（可用资金 + 持仓价值，持仓以成本价估算）
            total_position_value = self.get_position_cost()
            total_assets = self.get_total_assets()
            total_return = self.get_total_profit_rate()

            # 2. 利用DataFrame分析交易记录
            df = pd.DataFrame(self.transactions)
            stock_perf = {}  # 单股票盈亏分析

            if not df.empty:
                for code, trades in df.groupby('stock_code'):
                    buys = trades[trades['action'] == 'buy']
                    sells = trades[trades['action'] == 'sell']

                    # 问题1：买入和卖出金额统计方式有误，加上了所有buy/sell的commission，但实际上commission已在每笔买/卖成本中计算，应分别汇总
                    # 问题2：最大回撤（max_drawdown）统计不准确，这里只是单股票的最低收益率，实际应是收益率的最大下行幅度。这里只能作为简化统计理解。

                    if not buys.empty and not sells.empty:
                        # 【修正】买入成本=总买入金额+总买入佣金
                        buy_cost = (buys['price'] * buys['volume']).sum() + buys['commission'].sum()
                        # 卖出收入=总卖出金额-总卖出佣金-总卖出税
                        sell_income = (sells['price'] * sells['volume']).sum() - sells['commission'].sum() - sells['tax'].sum()
                        pl = sell_income - buy_cost
                        rr = (pl / buy_cost) * 100 if buy_cost != 0 else 0
                        stock_perf[code] = dict(return_rate=rr, buy_cost=buy_cost, sell_income=sell_income, profit_loss=pl)

            # 3. 简化统计汇总
            completed = list(stock_perf.values())
            total_completed = len(completed)
            win_rates = [x['return_rate'] for x in completed if x['return_rate'] > 0]
            loss_rates = [x['return_rate'] for x in completed if x['return_rate'] < 0]
            win_rate = (len(win_rates) / total_completed * 100) if total_completed else 0
            avg_profit_rate = sum(win_rates) / len(win_rates) if win_rates else 0
            avg_loss_rate = sum(loss_rates) / len(loss_rates) if loss_rates else 0
            # 【简化最大回撤】这里只是收益率极小值，非真正最大回撤
            max_drawdown = min([x['return_rate'] for x in completed], default=0)

            total_trades = len(self.transactions)
            total_commission = sum(t.get('commission', 0) for t in self.transactions)
            total_tax = sum(t.get('tax', 0) for t in self.transactions)
            total_costs = total_commission + total_tax

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
            info(f"最大回撤(个股): {max_drawdown:.2f}%")
            info(f"总手续费: {total_commission:,.2f} 元")
            info(f"总印花税: {total_tax:,.2f} 元")
            info(f"总交易成本: {total_costs:,.2f} 元")
            info("=" * 60)

            if stock_perf:
                info("各股票表现详情:")
                for code, v in stock_perf.items():
                    stat = "盈利" if v['return_rate'] > 0 else "亏损"
                    info(f"  {code}: {v['return_rate']:.2f}% ({stat})")

            return True
        except Exception as e:
            error(f"分析结果时发生错误: {e}")
            return False