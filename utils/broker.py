"""
模拟交易实现
"""
import configparser
from utils.logger import info, debug
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