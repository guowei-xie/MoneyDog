"""
突破前高涨停打板策略
选股：近90日实体最高价（max(开,收)）的 -10% 阈值，当前收盘价需大于该阈值。
买入：涨幅接近涨停 + 当日最低或昨日收盘低于前高 + 当前价高于前高。
卖出：当前涨停不卖；炸板立即清仓；否则按 MACD 首个顶/顶背离 分批卖出。
"""
import pandas as pd
from typing import List, Dict, Optional
import threading

from strategys.BaseStrategy import BaseStrategy
from utils.data import get_daily_bars, get_daily_bars_from_cache, has_index_1day_data
from utils.util import convert_to_safe_sell_volume, add_num_date_days
from laboratory.multipleK import get_macd, is_macd_top
from laboratory.singleK import is_limit, get_limit_price
from utils.logger import debug


class BreakPrevHighLimitUp(BaseStrategy):
    """
    突破前高涨停打板策略
    """

    def __init__(self):
        """
        初始化策略，选股可配参数放此处。
        """
        super().__init__()
        # 选股：回溯日线天数
        self.lookback_days = 90
        # 选股：近 N 日实体最高价的 -10% 作为阈值，即 阈值 = 实体最高价 * (1 - margin_pct)
        self.margin_pct = 0.10
        # 买入/选股：视为“接近涨停”的涨幅阈值（当前价或 T+1 最高价/昨收 >= 1+limit_near_pct）；选股未来函数与买入信号共用此参数
        self.limit_near_pct = 0.095
        # 卖出：分批次数（MACD 顶/顶背离 触发时）
        self.batch_sell_count = 2
        # 卖出：MACD 顶点判定所需最少分时 K 线数量
        self.sell_macd_min_bars = 5
        # 卖出：炸板判定，距离最近一次封板分钟数 >= N 即视为炸板
        self.sell_broken_limit_gap_minutes = 3
        # 选股：T~T-n 日区间振幅不能大于 m（n=区间交易日数，m=最大振幅，最高价/最低价-1）
        self.interval_days = 10
        self.interval_max_amplitude_pct = 0.20
        # 选股：近1年涨停次数不低于 min_limit_count；统计区间交易日数
        self.limit_count_check_days = 250
        self.min_limit_count = 1
        # 买入：仅在此时间窗内允许买入，用分时 bars 数量判断；第 90 根即 11:00（9:30 起算）
        self.buy_max_bars = 90
        # 指数闸门：中证1000（默认 000852.SH），用于盘前预选“总闸门”
        self.csi1000_index_code = "000852.SH"
        # 指数闸门缓存：避免多线程选股阶段并发读 DuckDB，并避免反复重算 MACD
        self._csi1000_macd_df: Optional[pd.DataFrame] = None
        self._csi1000_has_data: Optional[bool] = None
        self._csi1000_cache_loaded: bool = False  # 是否已完成一次加载尝试（无论是否成功）
        self._csi1000_cache_lock = threading.Lock()
        # 日志去重：避免每个交易日重复刷“跳过过滤”的提示
        self._csi1000_skip_logged: bool = False
        self._csi1000_load_failed_logged: bool = False

    def get_selected_stock_list(self, trade_date: str) -> List[str]:
        """
        获取自选股票列表（预买入）
        先借未来函数用 T+1 日最高涨幅缩池，再仅对缩池结果取 90 日线做实体前高筛选，减少行情数据量与内存占用。
        条件1（未来函数，仅用于缩池）：T+1 交易日最高涨幅 >= limit_near_pct，与买入“接近涨停”阈值一致。
        条件2：当前交易日收盘价 > 近 lookback_days 日实体最高价 * (1 - margin_pct)，且 T 日收盘价不能高于前高价；近90日最高价不含 T 日。
        条件3：T~T-n 日区间振幅不能大于 interval_max_amplitude_pct（n=interval_days），振幅=区间最高价/最低价-1。
        条件4：近 interval_days 个交易日不能有涨停。
        条件5：近 limit_count_check_days 日涨停次数不低于 min_limit_count。
        条件6：T 日日线 MACD 不能低于 T-1 日日线 MACD；但当 T 日 MACD 为正值时不做该判断。
        Args:
            trade_date: 交易日期
        Returns:
            List[str]: 自选股票列表
        """
        # 指数（中证1000）趋势过滤：若数据库存在该指数日线，则要求 T 日 MACD 不下行，否则当天放弃预选
        if not self._pass_csi1000_macd_gate(trade_date):
            return []

        next_trade_day = add_num_date_days(trade_date, 1, self.trade_calendar)
        # 1. 仅取 T+1 的 2 根 K 线（全市场），筛选出 T+1 最高涨幅 >= limit_near_pct 的股票，缩小后续取数范围
        if self._daily_bars_cache is not None:
            next_bars = get_daily_bars_from_cache(
                self._daily_bars_cache, self.global_stock_list, next_trade_day, 2
            )
        else:
            next_bars = get_daily_bars(
                self.global_stock_list,
                "1d",
                start_time="",
                end_time=next_trade_day,
                count=2,
            )
        t1_candidates = []
        for stock_code, df in next_bars.items():
            if df is None or df.empty or len(df) < 2:
                continue
            prev_close = float(df.iloc[-2]["close"])
            next_high = float(df.iloc[-1]["high"])
            if prev_close <= 0:
                continue
            if (next_high - prev_close) / prev_close >= self.limit_near_pct:
                t1_candidates.append(stock_code)
        if not t1_candidates:
            return []

        # 2. 取日线（需覆盖区间振幅与近1年涨停统计），再做实体前高与涨停相关筛选
        bars_count = max(self.lookback_days, self.limit_count_check_days)
        if self._daily_bars_cache is not None:
            daily_bars = get_daily_bars_from_cache(
                self._daily_bars_cache, t1_candidates, trade_date, bars_count
            )
        else:
            daily_bars = get_daily_bars(
                t1_candidates, "1d", start_time="", end_time=trade_date, count=bars_count
            )
        result = []
        min_bars = max(2, self.interval_days + 1)
        for stock_code, df in daily_bars.items():
            if df.empty or len(df) < min_bars:
                continue
            # 日线 MACD 过滤（正值放行；非正值要求不走弱）
            if not self._pass_daily_macd_filter(stock_code, df):
                continue
            df_before_t = df.iloc[:-1]
            entity_high = df_before_t[["open", "close"]].max(axis=1).max()
            threshold = entity_high * (1 - self.margin_pct)
            current_close = float(df.iloc[-1]["close"])
            if current_close <= threshold or current_close > entity_high:
                continue
            # T~T-n 日区间振幅 = 区间最高价/最低价 - 1，不能大于 interval_max_amplitude_pct
            interval_slice = df.iloc[-(self.interval_days + 1) :]
            interval_low = float(interval_slice["low"].min())
            if interval_low <= 0:
                continue
            amplitude = float(interval_slice["high"].max()) / interval_low - 1
            if amplitude > self.interval_max_amplitude_pct:
                continue
            # 近 interval_days 日不能有涨停
            recent = df.iloc[-self.interval_days:]
            if any(
                not pd.isna(row.get("preClose")) and is_limit(stock_code, row["close"], row["preClose"])
                for _, row in recent.iterrows()
            ):
                continue
            # 近1年涨停次数不低于 min_limit_count（参考 N_Pattern_Breakout_V2）
            last_n = df.iloc[-self.limit_count_check_days:] if len(df) >= self.limit_count_check_days else df
            limit_up_count = sum(
                1 for _, row in last_n.iterrows()
                if not pd.isna(row.get("preClose")) and is_limit(stock_code, row["close"], row["preClose"])
            )
            if limit_up_count < self.min_limit_count:
                continue
            result.append(stock_code)
        return result

    def _pass_csi1000_macd_gate(self, trade_date: str) -> bool:
        """
        盘前指数闸门（中证1000）：
        - 先从数据库检查是否有中证1000（默认按 000852.SH）指数的日线数据；
        - 若无数据：不影响原选股流程，直接放行；
        - 若有数据：取到 T 日的指数日线，计算 MACD，要求 T 日 MACD >= T-1 日 MACD（不能下行），否则当天放弃预选。

        Args:
            trade_date: 交易日（T 日），格式 'YYYYMMDD'

        Returns:
            bool: 通过闸门返回 True，否则 False
        """
        self._ensure_csi1000_cache_loaded(trade_date)
        if not self._csi1000_has_data:
            if not self._csi1000_skip_logged:
                debug(f"指数闸门: 数据库无中证1000日线({self.csi1000_index_code})，跳过指数过滤")
                self._csi1000_skip_logged = True
            return True

        macd_df = self._csi1000_macd_df
        if macd_df is None or macd_df.empty or len(macd_df) < 2:
            if not self._csi1000_load_failed_logged:
                debug("指数闸门: 中证1000日线/MACD加载失败或不足，跳过指数过滤（仅提示一次）")
                self._csi1000_load_failed_logged = True
            return True

        # 全量 MACD 已在加载时算好，这里只按交易日切片取最后两根
        macd_upto_t = macd_df.loc[macd_df.index <= trade_date]
        if len(macd_upto_t) < 2:
            debug(f"指数闸门: 中证1000日线不足(<=T)，跳过过滤 trade_date={trade_date}")
            return True

        macd_t = macd_upto_t.iloc[-1].get("macd")
        macd_t1 = macd_upto_t.iloc[-2].get("macd")
        if pd.isna(macd_t) or pd.isna(macd_t1):
            debug(f"指数闸门: 中证1000 MACD无效 macd_t={macd_t}, macd_t-1={macd_t1}，跳过过滤")
            return True

        macd_t = float(macd_t)
        macd_t1 = float(macd_t1)
        if macd_t < macd_t1:
            debug(
                f"指数闸门: 中证1000 MACD下行，放弃当天预选 trade_date={trade_date} macd_t={macd_t:.6f} < macd_t-1={macd_t1:.6f}"
            )
            return False
        return True

    def _ensure_csi1000_cache_loaded(self, trade_date: str) -> None:
        """
        确保中证1000指数缓存已初始化（一次完成、无论是否成功都不再重试）：
        - 缓存“是否存在指数日线数据”
        - 若存在则一次性加载全量日线并预计算 MACD，供后续按 trade_date 切片复用

        Args:
            trade_date: 当前交易日（用于兜底 end_time）
        """
        if self._csi1000_cache_loaded:
            return
        with self._csi1000_cache_lock:
            if self._csi1000_cache_loaded:
                return
            self._csi1000_has_data = bool(has_index_1day_data(self.csi1000_index_code))
            if self._csi1000_has_data:
                end_time = getattr(self, "backtest_end_time", "") or trade_date
                bars = get_daily_bars(
                    [self.csi1000_index_code],
                    "1d",
                    start_time="",
                    end_time=end_time,
                    count=-1,
                    table_name="index_daily",
                )
                df = bars.get(self.csi1000_index_code) if isinstance(bars, dict) else None
                if df is not None and not df.empty:
                    self._csi1000_macd_df = get_macd(df)
            self._csi1000_cache_loaded = True

    @staticmethod
    def _macd_last_two(daily_df: pd.DataFrame) -> Optional[tuple]:
        """对日线 df 计算 MACD 并返回 (macd_T, macd_T-1)；任一非法则返回 None。"""
        if daily_df is None or getattr(daily_df, "empty", True) or len(daily_df) < 2:
            return None
        macd_data = get_macd(daily_df)
        if macd_data is None or getattr(macd_data, "empty", True) or len(macd_data) < 2:
            return None
        macd_t = macd_data.iloc[-1].get("macd")
        macd_t1 = macd_data.iloc[-2].get("macd")
        if pd.isna(macd_t) or pd.isna(macd_t1):
            return None
        return float(macd_t), float(macd_t1)

    def _pass_daily_macd_filter(self, stock_code: str, daily_df: pd.DataFrame) -> bool:
        """
        预选股日线 MACD 过滤：
        - 若 T 日 MACD > 0：不做“不能低于昨日”的判断，直接放行；
        - 否则要求 T 日 MACD >= T-1 日 MACD（避免 MACD 走弱的标的进入预选池）。

        Args:
            stock_code: 股票代码（用于日志）
            daily_df: 覆盖到 T 日的日线数据（最后一行视为 T 日）
        Returns:
            bool: 通过过滤返回 True，否则 False
        """
        pair = self._macd_last_two(daily_df)
        if pair is None:
            debug(f"{stock_code} 预选过滤: 日线MACD数据不足或无效")
            return False
        macd_t, macd_t1 = pair
        if macd_t > 0:
            return True
        if macd_t < macd_t1:
            debug(f"{stock_code} 预选过滤: 日线MACD走弱 macd_t={macd_t:.6f} < macd_t-1={macd_t1:.6f}")
            return False
        return True

    def set_cached(self, trade_date: str) -> bool:
        """
        缓存盘前数据：昨日收盘价、前高价格线（与选股一致），供盘中买入信号使用。
        Args:
            trade_date: 交易日期（当日收盘价即“昨日收盘价”）
        Returns:
            bool: 是否成功
        """
        self.cached = {}
        stock_list = self.selected_stock_list + self.holding_stock_list
        if not stock_list:
            return True
        daily_bars = get_daily_bars(
            stock_list, "1d", start_time="", end_time=trade_date, count=self.lookback_days
        )
        for stock_code, daily_bar in daily_bars.items():
            if daily_bar.empty or len(daily_bar) < 2:
                continue
            self.cached[stock_code] = {}
            # 昨日收盘价（当日分时对应的“昨收”）
            self.cached[stock_code]["pre_close"] = float(daily_bar.iloc[-1]["close"])
            # 前高价格线：近 N 日实体最高价不含 T 日，与选股逻辑一致
            bar_before_t = daily_bar.iloc[:-1]
            entity_high = bar_before_t[["open", "close"]].max(axis=1).max()
            self.cached[stock_code]["prev_high_price"] = float(entity_high)
            # 卖出：分批剩余次数、分时 MACD 顶点记录（用于顶背离判断）
            self.cached[stock_code]["batch_sell_count"] = self.batch_sell_count
            self.cached[stock_code]["top_price"] = 0.0
            self.cached[stock_code]["top_macd"] = 0.0
        return True

    def _is_intraday_macd_rising(self, stock_code: str, bars: pd.DataFrame) -> bool:
        """
        判断分时 MACD 是否走强：当前分时 MACD 必须严格大于上一根分时 MACD。

        Args:
            stock_code: 股票代码（用于日志）
            bars: 分时K线快照（DataFrame）
        Returns:
            bool: 满足条件返回 True，否则 False
        """
        if bars is None or getattr(bars, "empty", True) or len(bars) < 2:
            return False
        macd_data = get_macd(bars)
        if macd_data is None or getattr(macd_data, "empty", True) or len(macd_data) < 2:
            return False
        current_macd = macd_data.iloc[-1].get("macd")
        prev_macd = macd_data.iloc[-2].get("macd")
        if pd.isna(current_macd) or pd.isna(prev_macd):
            debug(f"{stock_code} 分时MACD无效: current={current_macd}, prev={prev_macd}")
            return False
        return float(current_macd) > float(prev_macd)

    def buy_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        买入信号：同时满足 (1)涨幅接近涨停 (2)当日最低或昨日收盘低于前高 (3)当前分时价高于前高；
        且当前分时之前未出现过涨幅>limit_near_pct，开盘价涨幅也不超过 limit_near_pct；
        且当前分时 MACD 大于上一根分时 MACD；
        且仅在 9:30~11:00 内买入（分时 bars 数量 <= buy_max_bars，第 90 根即 11:00）。
        Args:
            stock_code: 股票代码
            bars: 分时K线快照（DataFrame）
        Returns:
            Optional[Dict]: 买入信号字典，无信号返回 None
        """
        if stock_code in self.broker.positions:
            return None
        if bars.empty or stock_code not in self.cached:
            return None
        # 买入时间窗：仅 9:30~11:00，第 90 根分时线对应 11:00
        if len(bars) > self.buy_max_bars:
            return None
        pre_close = self.cached[stock_code]["pre_close"]
        prev_high = self.cached[stock_code]["prev_high_price"]
        if pre_close <= 0:
            return None
        limit_threshold = pre_close * (1 + self.limit_near_pct)
        current_price = float(bars.iloc[-1]["close"])
        intraday_low = float(bars["low"].min())

        # 开盘价涨幅不能大于 limit_near_pct
        day_open = float(bars.iloc[0]["open"])
        if day_open > limit_threshold:
            return None
        # # 当前分时之前，没有发生过涨幅大于 limit_near_pct（此前 bars 的最高价未超过该涨幅）
        # if len(bars) > 1:
        #     high_before_current = float(bars.iloc[:-1]["high"].max())
        #     if high_before_current >= limit_threshold:
        #         return None

        # 1. 当前涨幅是否接近涨停：当前分时价/昨日收盘价 >= limit_near_pct
        if current_price / pre_close < (1 + self.limit_near_pct):
            return None
        # 2. 当日分时最低价或昨日收盘价是否低于前高价格线（满足其一即可）
        if intraday_low >= prev_high and pre_close >= prev_high:
            return None
        # 3. 当前分时价格是否已高于前高价格线
        if current_price <= prev_high:
            return None

        # 4. 当前分时 MACD 必须大于上一根分时 MACD
        if not self._is_intraday_macd_rising(stock_code, bars):
            debug(f"{stock_code} 买入过滤: 分时MACD未走强")
            return None

        buy_volume = self.broker.get_buy_volume(current_price)
        if buy_volume <= 0:
            return None
        return {
            "action": "buy",
            "stock_code": stock_code,
            "price": current_price,
            "volume": buy_volume,
            "minute_k_count": len(bars),
            "time": bars.index[-1],
            "desc": "突破前高涨停打板",
        }

    def _check_macd_top_gate(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict[str, float]]:
        """
        分时 MACD 顶点过滤：出现顶点且满足（首个顶 / 低于上一顶点价 / 顶背离）之一。
        参考 N_Pattern_Breakout_V2。
        """
        if bars is None or getattr(bars, "empty", True) or len(bars) < self.sell_macd_min_bars:
            return None
        macd_data = get_macd(bars)
        if not is_macd_top(macd_data):
            return None
        current_price = float(bars.iloc[-1]["close"])
        current_macd = float(macd_data.iloc[-1]["macd"])
        last_top_price = float(self.cached[stock_code].get("top_price", 0.0) or 0.0)
        last_top_macd = float(self.cached[stock_code].get("top_macd", 0.0) or 0.0)
        is_first_top = last_top_price <= 0
        is_lower_than_last = last_top_price > 0 and current_price < last_top_price
        is_divergence = (
            last_top_price > 0
            and last_top_macd != 0
            and current_price >= last_top_price
            and current_macd < last_top_macd
        )
        if not (is_first_top or is_lower_than_last or is_divergence):
            return None
        return {
            "current_price": current_price,
            "current_macd": current_macd,
            "last_top_price": last_top_price,
            "last_top_macd": last_top_macd,
        }

    def _update_top_cache(self, stock_code: str, top_price: float, top_macd: float) -> None:
        """更新分时 MACD 顶点缓存，供下一根 K 顶背离比较用。"""
        self.cached[stock_code]["top_price"] = float(top_price)
        self.cached[stock_code]["top_macd"] = float(top_macd)

    def _get_sell_volume_by_batch(self, stock_code: str, available_volume: int) -> int:
        """按剩余分批次数计算本次卖出量，返回 100 整数倍。"""
        batch_sell_count = max(
            int(self.cached[stock_code].get("batch_sell_count", self.batch_sell_count) or self.batch_sell_count),
            1,
        )
        plan_volume = available_volume // batch_sell_count
        return convert_to_safe_sell_volume(plan_volume, available_volume)

    def _sell_broken_limit(
        self, stock_code: str, bars: pd.DataFrame, yesterday_close: float, available_volume: int
    ) -> Optional[Dict]:
        """
        炸板清仓：曾触及涨停且当前价低于涨停价，且距最近一次封板 >= N 分钟则立即全卖。
        """
        current_price = float(bars.iloc[-1]["close"])
        limit_price_up = float(get_limit_price(stock_code, yesterday_close, "up"))
        if bars["high"].max() < limit_price_up or current_price >= limit_price_up:
            return None
        limit_close_idx = bars.index[bars["close"] >= limit_price_up]
        if len(limit_close_idx) <= 0:
            return None
        last_limit_pos = int(bars.index.get_loc(limit_close_idx[-1]))
        gap = (len(bars) - 1) - last_limit_pos
        if gap < self.sell_broken_limit_gap_minutes:
            return None
        debug(f"{stock_code} 触发炸板清仓: gap={gap}")
        return {
            "action": "sell",
            "stock_code": stock_code,
            "price": current_price,
            "volume": int(available_volume),
            "minute_k_count": len(bars),
            "time": bars.index[-1],
            "desc": "止盈（炸板）",
        }

    def _sell_batch_on_macd_top(
        self, stock_code: str, bars: pd.DataFrame, available_volume: int, top_ctx: Dict[str, float]
    ) -> Optional[Dict]:
        """MACD 首个顶或顶背离时分批卖出（次日默认卖出模式）。"""
        current_price = top_ctx["current_price"]
        current_macd = top_ctx["current_macd"]
        sell_volume = self._get_sell_volume_by_batch(stock_code, available_volume)
        if sell_volume <= 0:
            return None
        self.cached[stock_code]["batch_sell_count"] = max(
            int(self.cached[stock_code].get("batch_sell_count", self.batch_sell_count)) - 1, 0
        )
        self._update_top_cache(stock_code, current_price, current_macd)
        return {
            "action": "sell",
            "stock_code": stock_code,
            "price": current_price,
            "volume": sell_volume,
            "minute_k_count": len(bars),
            "time": bars.index[-1],
            "desc": "止盈（MACD顶/顶背离）",
        }

    def sell_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        卖出信号：当前涨停不卖；炸板则立即清仓；否则按 MACD 首个顶/顶背离 分批卖出。
        """
        if bars.empty or stock_code not in self.cached:
            return None
        available_volume = int(self.broker.get_available_volume(stock_code))
        if available_volume <= 0:
            return None
        yesterday_close = float(self.cached[stock_code]["pre_close"])
        current_price = float(bars.iloc[-1]["close"])

        # 若当前涨停则拒绝卖出
        if is_limit(stock_code, current_price, yesterday_close):
            return None

        # 炸板则立即清仓
        signal_broken = self._sell_broken_limit(stock_code, bars, yesterday_close, available_volume)
        if signal_broken is not None:
            return signal_broken

        # MACD 首个顶或顶背离 → 分批卖出
        top_ctx = self._check_macd_top_gate(stock_code, bars)
        if top_ctx is not None:
            return self._sell_batch_on_macd_top(stock_code, bars, available_volume, top_ctx)

        return None

    def on_minute_end(self, stock_code: str, bars: pd.DataFrame) -> None:
        """分钟结束若出现分时 MACD 顶点，更新顶点缓存，供顶背离判断。"""
        if stock_code not in self.cached:
            return
        if bars is None or getattr(bars, "empty", True) or len(bars) < self.sell_macd_min_bars:
            return
        macd_data = get_macd(bars)
        if is_macd_top(macd_data):
            self._update_top_cache(
                stock_code,
                top_price=float(bars.iloc[-1]["close"]),
                top_macd=float(macd_data.iloc[-1]["macd"]),
            )