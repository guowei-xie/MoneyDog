"""
模拟撮合 Broker 的费用/持仓金标准单测。

Broker.__init__ 会读取 config.ini，这里构造后显式覆盖资金与费率字段，
使断言与 config.ini 内容无关、可离线重复运行。
"""
import pytest

from utils.broker import Broker


def _broker(commission_rate=0.0003, min_commission=5.0, tax_rate=0.001,
            available=100000.0, limit_vol_type="amount",
            max_vol_amount=100000.0, max_vol_rate=0.05):
    b = Broker()
    b.commission_rate = commission_rate
    b.min_commission = min_commission
    b.tax_rate = tax_rate
    b.initial_amount = available
    b.available_amount = available
    b.limit_vol_type = limit_vol_type
    b.max_vol_amount = max_vol_amount
    b.max_vol_rate = max_vol_rate
    b.positions = {}
    b.transactions = []
    b.position_and_account_changes = []
    return b


def _buy_signal(code="000001.SZ", price=10.0, volume=1000):
    return {"action": "buy", "stock_code": code, "price": price, "volume": volume,
            "time": "20250101093000", "desc": "test", "minute_k_count": 1}


def _sell_signal(code="000001.SZ", price=11.0, volume=1000):
    return {"action": "sell", "stock_code": code, "price": price, "volume": volume,
            "time": "20250101150000", "desc": "test", "minute_k_count": 240}


class TestBuy:
    def test_buy_deducts_amount_and_percentage_commission(self):
        b = _broker()
        assert b.buy(_buy_signal(price=50.0, volume=1000)) is True
        # total=50000, 佣金=max(50000*0.0003=15, 5)=15（走比例，非下限）, cost_all=50015
        assert b.available_amount == pytest.approx(100000 - 50015)
        pos = b.positions["000001.SZ"]
        assert pos["cost_price"] == pytest.approx(50.0)
        assert pos["volume"] == 1000

    def test_commission_floor_applied(self):
        b = _broker(commission_rate=0.0003)
        b.buy(_buy_signal(price=10.0, volume=1000))  # 3 < 5 → 收 5
        assert b.available_amount == pytest.approx(100000 - 10005)

    def test_buy_rejected_when_insufficient_funds(self):
        b = _broker(available=1000.0)
        assert b.buy(_buy_signal(price=10.0, volume=1000)) is False  # 需 10005 > 1000
        assert b.positions == {}

    def test_buy_rejected_when_zero_volume(self):
        b = _broker()
        assert b.buy(_buy_signal(volume=0)) is False


class TestSell:
    def test_sell_credits_net_of_commission_and_tax(self):
        b = _broker()
        b.buy(_buy_signal(price=10.0, volume=1000))
        b.unlock_position()  # 解锁买入锁定，使可卖量=1000
        assert b.sell(_sell_signal(price=11.0, volume=1000)) is True
        # 卖出 total=11000, 佣金=max(3.3,5)=5, 印花税=11000*0.001=11 → 净入 10984
        expected_avail = (100000 - 10005) + (11000 - 5 - 11)
        assert b.available_amount == pytest.approx(expected_avail)
        assert b.positions["000001.SZ"]["volume"] == 0

    def test_sell_rejected_when_volume_exceeds_available(self):
        b = _broker()
        b.buy(_buy_signal(volume=1000))
        b.unlock_position()
        assert b.sell(_sell_signal(volume=2000)) is False


class TestSetPositionWeightedCost:
    def test_add_uses_volume_weighted_average_cost(self):
        b = _broker()
        b.set_position("X", cost_price=10.0, volume=1000)
        b.set_position("X", cost_price=12.0, volume=1000)
        # 加权成本 = (10*1000 + 12*1000)/2000 = 11
        assert b.positions["X"]["cost_price"] == pytest.approx(11.0)
        assert b.positions["X"]["volume"] == 2000
        # 新增部分被锁定
        assert b.positions["X"]["disabled_volume"] == 1000

    def test_reduce_keeps_cost_unchanged(self):
        b = _broker()
        b.set_position("X", cost_price=10.0, volume=1000)
        b.set_position("X", cost_price=999.0, volume=-400)  # 减仓不改成本
        assert b.positions["X"]["cost_price"] == pytest.approx(10.0)
        assert b.positions["X"]["volume"] == 600


class TestGetBuyVolume:
    def test_amount_mode_rounds_down_to_lot(self):
        b = _broker(limit_vol_type="amount", max_vol_amount=50000.0, available=100000.0)
        # 50000/33 = 1515.15 → 向下取整百 → 1500
        assert b.get_buy_volume(33.0) == 1500

    def test_returns_zero_when_below_one_lot(self):
        b = _broker(limit_vol_type="amount", max_vol_amount=5000.0, available=100000.0)
        # 5000/100 = 50 → 向下取整百 → 0 → 返回 0
        assert b.get_buy_volume(100.0) == 0

    def test_capped_by_affordable_amount(self):
        b = _broker(limit_vol_type="amount", max_vol_amount=100000.0, available=10000.0)
        # 目标 100000/50=2000，但可用资金仅够 10000/50=200 → 取 200
        assert b.get_buy_volume(50.0) == 200
