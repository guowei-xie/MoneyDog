"""
高量能 Top2 开盘买入策略

盘前选股（以选股日 T 的日线为基准，与框架一致：T 选股、T+1 分时回测）：
1）T 日成交量不低于近 100 日成交量序列的 95% 分位数
2）T 日收盘价 > 85
3）在上述候选中按日线量比取前 2（量比见 utils.volume_ratio.compute_volume_ratio_daily）

盘中：开盘第一根分钟 K 线（累计仅 1 根）以最新价（该根收盘价）买入；
      当日最后一根分钟 K 线判断：相对持仓成本亏损 >= 4% 或盈利 >= 8% 则清仓；
      另：自建仓日起算，持仓交易日数大于 max_hold_trading_days 时，仍在尾盘最后一分钟清仓。
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from strategys.BaseStrategy import BaseStrategy
from utils.data import get_daily_bars
from utils.logger import debug
from utils.util import add_num_date_days, convert_to_safe_sell_volume
from utils.volume_ratio import compute_volume_ratio_daily


class VolumePercentileTop2Strategy(BaseStrategy):
    """近 100 日放量筛选后按量比取前 2，开盘首分钟买入，尾盘止损止盈。"""

    def __init__(self) -> None:
        super().__init__()
        self.lookback_days = 100
        self.volume_percentile = 95.0
        self.min_close_price = 85.0
        self.top_n_by_volume_ratio = 2
        self.volume_ratio_avg_days = 5
        self.stop_loss_pct = 0.04
        self.take_profit_pct = 0.08
        # 持仓交易日数 > 该值时，尾盘清仓（不含建仓当日则为第 6 个交易日起可触发）
        self.max_hold_trading_days = 5
        self._last_minute_of_day: Optional[str] = None
        self._current_session_date: Optional[str] = None
        self._entry_session_date: Dict[str, str] = {}

    def before_open(self, trade_date: str) -> bool:
        self._current_session_date = add_num_date_days(trade_date, 1, self.trade_calendar)
        ok = super().before_open(trade_date)
        if ok and self.minute_snapshots:
            self._last_minute_of_day = str(self.minute_snapshots[-1]["minute"])
        else:
            self._last_minute_of_day = None
        return ok

    def get_selected_stock_list(self, trade_date: str) -> List[str]:
        """
        按 T 日日线筛选；量比降序取前 top_n_by_volume_ratio。
        """
        need = max(self.lookback_days, self.volume_ratio_avg_days + 1)
        daily_bars = self.get_daily_bars_for_selection(trade_date, count=need + 5)
        scored: List[tuple] = []
        for stock_code, df in daily_bars.items():
            if df is None or df.empty or len(df) < self.lookback_days:
                continue
            window = df.iloc[-self.lookback_days :]
            vols = window["volume"].astype(float)
            v_today = float(df.iloc[-1]["volume"])
            if v_today <= 0:
                continue
            p_thr = float(np.percentile(vols.values, self.volume_percentile))
            if v_today < p_thr:
                continue
            close_px = float(df.iloc[-1]["close"])
            if close_px <= self.min_close_price:
                continue
            vr = compute_volume_ratio_daily(df, self.volume_ratio_avg_days)
            if vr != vr or vr <= 0:
                continue
            scored.append((stock_code, vr))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c[0] for c in scored[: self.top_n_by_volume_ratio]]

    def set_cached(self, trade_date: str) -> bool:
        self.cached = {}
        stock_list = self.selected_stock_list + self.holding_stock_list
        if not stock_list:
            return True
        daily_bars = get_daily_bars(
            stock_list, "1d", start_time="", end_time=trade_date, count=2
        )
        for stock_code in stock_list:
            df = daily_bars.get(stock_code)
            if df is not None and not df.empty:
                self.cached[stock_code] = {
                    "pre_close": float(df.iloc[-1]["close"]),
                }
            else:
                self.cached[stock_code] = {}
        return True

    def trade(self, signal: Dict) -> bool:
        action = signal.get("action")
        stock_code = signal.get("stock_code")
        if action == "buy":
            if not self.broker.buy(signal):
                return False
            if self._current_session_date is not None and stock_code:
                self._entry_session_date[stock_code] = self._current_session_date
            return True
        if action == "sell":
            if not self.broker.sell(signal):
                return False
            if stock_code and self.broker.positions.get(stock_code, {}).get("volume", 0) == 0:
                self._entry_session_date.pop(stock_code, None)
            return True
        return True

    def _held_trading_days_inclusive(self, stock_code: str) -> int:
        """建仓当日至当前分时日（含首尾）的交易日数；无建仓记录返回 0。"""
        entry = self._entry_session_date.get(stock_code)
        cur = self._current_session_date
        if not entry or not cur:
            return 0
        if entry not in self.trade_calendar or cur not in self.trade_calendar:
            return 0
        return self.trade_calendar.index(cur) - self.trade_calendar.index(entry) + 1

    def buy_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        if stock_code in self.broker.positions:
            return None
        if bars is None or bars.empty or len(bars) != 1:
            return None
        price = float(bars.iloc[-1]["close"])
        buy_volume = self.broker.get_buy_volume(price)
        if buy_volume <= 0:
            return None
        return {
            "action": "buy",
            "stock_code": stock_code,
            "price": price,
            "volume": buy_volume,
            "minute_k_count": len(bars),
            "time": bars.index[-1],
            "desc": "开盘首分钟买入",
        }

    def sell_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        if self._last_minute_of_day is None:
            return None
        if bars is None or bars.empty:
            return None
        if str(bars.index[-1]) != self._last_minute_of_day:
            return None
        available_volume = int(self.broker.get_available_volume(stock_code))
        if available_volume <= 0:
            return None
        cost = float(self.broker.get_position_cost_price(stock_code))
        if cost <= 0:
            return None
        price = float(bars.iloc[-1]["close"])
        pnl_pct = price / cost - 1.0
        held = self._held_trading_days_inclusive(stock_code)
        force_time_exit = held > self.max_hold_trading_days
        if not force_time_exit:
            if pnl_pct > -self.stop_loss_pct and pnl_pct < self.take_profit_pct:
                return None
        sell_volume = convert_to_safe_sell_volume(available_volume, available_volume)
        if sell_volume <= 0:
            return None
        if force_time_exit:
            desc = f"持仓>{self.max_hold_trading_days}日尾盘清仓"
            debug(
                f"{stock_code} {desc}: 已持{held}个交易日 成本={cost:.3f} 现价={price:.3f}"
            )
        else:
            desc = "止损" if pnl_pct <= -self.stop_loss_pct else "止盈"
            debug(
                f"{stock_code} 尾盘{desc}: 成本={cost:.3f} 现价={price:.3f} 盈亏率={pnl_pct*100:.2f}%"
            )
        return {
            "action": "sell",
            "stock_code": stock_code,
            "price": price,
            "volume": sell_volume,
            "minute_k_count": len(bars),
            "time": bars.index[-1],
            "desc": f"尾盘{desc}"
            + ("" if force_time_exit else "（-4%/+8%）"),
        }
