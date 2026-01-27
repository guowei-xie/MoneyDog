## MA5 底部确认策略（与当前代码实现保持同步说明）

### 一、整体思路
- **选股阶段（日线）**  
  - 基于 5 日均线（MA5）的“底部抬高”形态：当日收盘价突破 MA5，且前一日为 MA5 底部，并且该 MA5 底部高于前一次 MA5 底部。  
  - 要求股价位于 5 元 ~ 60 元之间，只在预设股票池中运行。  
  - 同时要求中期趋势向上（MA30 向上），过滤掉大部分逆势个股。  
- **买入阶段（分时）**  
  - 盘中只在开盘第 1 分钟直接买入，无其它分时形态约束。  
- **卖出阶段（分时 + 日线）**  
  - 止盈：基于日线 MACD 红柱缩短 + 当前价低于昨收，在 14:30 之后触发。  
  - 止损：以建仓日前 3 个交易日的最低价作为止损线，盘中跌破止损线则止损卖出。

---

### 二、选股条件（对应 `_select_stock`）
- **条件0：价格区间限制**  
  - 使用最新一日收盘价作为参考价。  
  - 要求 `price_min <= close <= price_max`，代码中为 \[5, 60] 元。  
  - 若不满足直接过滤。

- **条件1 补充：K 线形态与涨停过滤**  
  - 最新一日不能为阴线：`close > open`。  
  - 最新一日不能是涨停：使用前一日收盘价与当日收盘价，通过 `is_limit(..., limit_type='up')` 判断。  

- **条件1：T 日收盘价站上 MA5**  
  - 计算最近一段时间的 MA5（`get_ma_list(period=5)`），要求样本数 ≥ 5。  
  - 条件为：  
    - 当日收盘价 > 当日 MA5；  
    - 前一日收盘价 < 前一日 MA5。  
  - 即从“跌破 MA5”重新站上 MA5，视作短期趋势反转。

- **条件2 补充：MA30 中期趋势向上**  
  - 使用 `get_ma_list(period=30)` 计算 MA30。  
  - 至少需要 31 个有效样本，且最后两日 MA30 都非空。  
  - 要求 `MA30_T > MA30_T-1`，表示中期均线拐头向上。

- **条件2：T-1 日为 MA5 底部**  
  - 使用 `get_ma5_bottom(left_count=5, right_count=1)` 标记 MA5 底部。  
  - 要求倒数第二根（T-1 日）对应的 `is_ma5_bottom` 为 True。  
  - 即前一日为 MA5 底部拐点。

- **条件3：MA5 底部抬高**  
  - 再次使用 `get_ma5_bottom(left_count=5, right_count=5)` 获取更完整的 MA5 底部序列。  
  - 取 T-1 日对应的 `ma5` 作为当前底部 MA5：`current_bottom_ma5`。  
  - 在 T-1 日之前的所有记录中，筛选 `is_ma5_bottom=True` 的历史底部：`previous_bottoms`。  
  - 若历史中不存在底部，或最近一次历史底部 `previous_bottom_ma5` 为空，则不通过。  
  - 要求：`current_bottom_ma5 > previous_bottom_ma5`，即当前 MA5 底部高于上一次 MA5 底部，构成“底部抬高”的上升结构。

---

### 三、缓存逻辑（对应 `set_cached`）
- **盘前缓存内容**  
  - 对“自选股列表 + 当前持仓列表”集合中的所有股票：  
    - 拉取最近 90 个交易日的日线数据 `daily_bar`，写入缓存 `self.cached[stock_code]['daily_bar']`。  
    - 若该股票为持仓股，则计算止损线并一并缓存。  

- **止损线的预计算**  
  - 通过 `_calculate_stop_loss_price` 完成，详见后文。  
  - 缓存键为 `self.cached[stock_code]['stop_loss_price']`。  
  - 盘中止损判断直接使用缓存值，避免重复计算与数据拉取。

---

### 四、买入信号（对应 `buy_signal`）
- **买入时机：仅第 1 分钟**  
  - 买入函数只在 `len(bars) == 1` 时返回买入信号，即仅在开盘第 1 根分时 K 线结束时尝试建仓。  
  - 不做额外的 MACD、均线、分时形态等判断，逻辑非常简单直接。  

- **买入价格与数量**  
  - 买入价格：使用当前分时 K 线的收盘价 `bars.iloc[-1]['close']`。  
  - 买入数量：通过 `self.broker.get_buy_volume(price)` 动态计算，交由券商/资金管理模块控制。  
  - 返回的信号中会记录 `action='buy'`、`stock_code`、`price`、`volume`、`time` 以及说明文本“第1分钟买入”。

---

### 五、卖出信号（对应 `sell_signal`）
- **前置条件**  
  - 仅在持仓可用数量 `available_volume > 0` 时才考虑卖出。  

- **卖出流程**  
  1. 优先检查止盈信号 `_sell_signal_1`：若触发，按全部可用数量卖出并返回。  
  2. 若未触发止盈，则检查止损信号 `_sell_signal_2`：若有止损信号则返回；  
  3. 若两者都不触发，则本周期不卖出。

---

### 六、止盈逻辑（对应 `_sell_signal_1`）
- **基础条件**  
  - 需要存在有效的缓存日线数据 `self.cached[stock_code]['daily_bar']`，且长度 ≥ 2。  
  - 分时数据 `bars` 非空。  

- **时间过滤**  
  - 仅在 14:30 之后才判断止盈：  
    - 使用“每分钟一根 K 线”的假设，要求 `len(bars) >= 210`，约等于 210 分钟（14:30 后）。  

- **价格条件**  
  - 昨日收盘价：`yesterday_close = daily_bar.iloc[-1]['close']`。  
  - 当前价：`current_price = bars.iloc[-1]['close']`。  
  - 要求当前价 **不高于** 昨日收盘价：`current_price <= yesterday_close`，否则不卖（仍在相对强势）。  

- **动态 MACD 判断（日级别）**  
  - 使用当前分时数据 `bars` 动态拼接“今日日 K”：`dynamic_daily_kline = get_dynamic_daily_kline(bars)`。  
  - 将历史日线 `daily_bar` 与动态日线拼接后计算 MACD：`macd_data = get_macd(dynamic_klines)`。  
  - 要求 MACD 序列长度 ≥ 2，取：  
    - 今日 MACD 柱：`today_macd_bar = macd_data.iloc[-1]['macd']`；  
    - 昨日 MACD 柱：`yesterday_macd_bar = macd_data.iloc[-2]['macd']`。  
  - 条件：  
    - 昨日 MACD 必须 > 0（红柱区域）；  
    - 今日 MACD 柱 < 昨日 MACD 柱（红柱缩短）。  
  - 满足以上条件则视为日线 MACD 出现减弱信号，结合当前价低于昨收，触发止盈卖出。

---

### 七、止损逻辑（对应 `_sell_signal_2` 与 `_calculate_stop_loss_price`）
- **止损线的计算 `_calculate_stop_loss_price`**  
  - 通过券商接口获取建仓日期：`build_date = self.broker.get_build_date(stock_code)`。  
  - 在缓存的日线数据 `daily_bar` 中找到建仓日所在索引 `build_idx`。  
  - 要求建仓日前至少有 3 根 K 线（T-1、T-2、T-3），即 `build_idx >= 3`，否则不计算止损线。  
  - 取建仓日前 3 天的日线子区间：`window_df = df.iloc[build_idx-3:build_idx]`。  
  - 使用该窗口内的 `low` 列最小值作为止损线：`stop_loss_price = min(low)`。  
  - 若值为 NaN 或 ≤ 0，则视为无效。  

- **止损信号 `_sell_signal_2`**  
  - 盘前通过 `set_cached` 已将 `stop_loss_price` 写入 `self.cached[stock_code]['stop_loss_price']`，若不存在则不止损。  
  - 分时价格：`current_price = bars.iloc[-1]['close']`。  
  - 当 `current_price < stop_loss_price` 时：  
    - 获取可用卖出数量 `available_volume`；  
    - 若 `available_volume > 0`，则生成卖出信号：  
      - `action='sell'`，价格为当前分时价，数量为全部可用数量；  
      - 文本中会标注止损线价格与建仓价格（`build_price`）。  

---

### 八、策略特点总结
1. **趋势与结构双重确认**  
   - 通过“MA5 底部抬高 + MA30 向上”确认股票处于中短期上升结构。  
   - 要求 MA5 底部逐级抬升，避免单次反弹的假信号。  

2. **买入时点极简**  
   - 只在开盘第 1 分钟建仓，不做复杂分时判断，适合自动化执行。  

3. **日线 MACD 止盈**  
   - 利用日线 MACD 红柱缩短 + 当前价低于昨收的组合，识别上涨动能减弱区域，避免在高位被动回撤。  

4. **建仓前低点止损**  
   - 以建仓前三日最低价为止损线，相当于用“上一个小波段低点”保护仓位，控制单笔风险。  

5. **实现简洁，可维护性强**  
   - 选股逻辑集中在 MA5/MA30 与底部形态，分时逻辑非常轻量，便于后续调整与扩展。


