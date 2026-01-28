## N字战法-突破策略V2（与当前代码实现保持同步说明）

### 一、整体思路
- **选股阶段（日线）**
  - 基于“N字战法”，优先选择近期出现涨停（首板/二板），随后出现“涨停次日放量 + 缩量整理”的结构。
  - 额外要求价格不跌破“最近一次 MA5 顶部（均线值）”形成的支撑，并控制近端波动（振幅）与历史活跃度（近1年涨停次数）。
- **买入阶段（分时 + 动态日线）**
  - 在“价格回到 T 日收盘价附近（±N%）且不追高”的前提下，等待分时 MACD 底部 + 日内突破昨日实体上沿 + 价格强于分时均价。
  - 同时用“动态日线 MACD 红柱增强（高于昨日）”做趋势确认，避免弱势反弹。
- **卖出阶段（分时）**
  - 组合化卖出：炸板清仓（优先级最高）、分批止盈、分批止损。
  - 在涨停状态下进行卖出保护：**当前涨停不卖出**。

---

### 二、选股条件（对应 `_select_stock`）
> 说明：以下条件需同时满足。

- **条件0：价格区间过滤**
  - 使用最新一日收盘价 `close`。
  - 要求 `price_min <= close <= price_max`，当前代码为 \[5, 100]。

- **条件1：近 N 日存在涨停，且最近一次涨停为首板/二板**
  - 在近 `limit_check_days=5` 个交易日内，必须能找到最近一次涨停日 `T`。
  - 计算 `T` 日截至的连板数（板数）`limit_board_number`，要求 `1 <= limit_board_number <= max_limit_board(=2)`。

- **条件2：距离 T 日至少间隔 N 个交易日**
  - 从 `T` 日到最新交易日的样本长度必须满足 `len(focused_bars) > min_days_after_limit(=3)`。

- **条件3：T+1 日成交量为近 N 日最大**
  - 取近 `volume_check_days=20` 日的最大成交量 `max_volume_n`。
  - 要求 `T+1` 日成交量 `volume(T+1) >= max_volume_n`。

- **条件4：T+1 至今逐日缩量**
  - 对 `T+1` 日起的日线序列，要求成交量逐日递减（`is_volume_decreasing` 判定）。

- **条件5：自 T 日起，收盘价不跌破最近一次 MA5 顶部“均线价格”**
  - 先在 `T` 日之前寻找最近一次 MA5 顶部（`get_ma5_top(...)[is_ma5_top=True]`）。
  - 使用该顶部的 `ma5` 值作为支撑价 `last_ma5_top_price`（注意：不是顶部当日收盘价）。
  - 要求从 `T` 日起的所有收盘价满足：`min(close[T:]) >= last_ma5_top_price`。

- **条件6：近 N 日区间振幅限制**
  - 取最近 `amplitude_check_days=20` 个交易日：
  - 振幅定义为：`amplitude = highest(high) / lowest(low) - 1`。
  - 要求 `amplitude <= max_amplitude(=0.5)`。

- **条件7：近 1 年涨停次数不少于 N 次**
  - 在近 `limit_count_check_days=250` 个交易日内统计涨停次数（数据不足则用已有数据）。
  - 要求 `limit_up_count >= min_limit_count(=6)`。

---

### 三、盘前缓存逻辑（对应 `set_cached`）
- **缓存范围**
  - `stock_list = selected_stock_list + holding_stock_list`。
  - 拉取最近 60 个交易日的日线 `daily_bar` 写入 `cached[stock_code]['daily_bar']`。

- **卖出相关缓存（每日盘前重置）**
  - `cached[stock_code]['batch_sell_count'] = batch_sell_count`（默认 2，表示分批卖出剩余次数）。
  - `cached[stock_code]['top_price'] = 0.0`、`cached[stock_code]['top_macd'] = 0.0`（用于“分时 MACD 顶点比较/顶背离”）。

- **买入相关缓存**
  - `cached[stock_code]['t_day_close']`：近 `limit_check_days` 内最近一次涨停日 `T` 的收盘价（找不到则为 `None`）。
  - `cached[stock_code]['last_ma5_top_price']`：最近一次 MA5 顶部对应的 `ma5` 值（找不到则为 `None`）。

---

### 四、买入信号（全部满足，对应 `buy_signal`）
> 说明：买入信号只在“当前无持仓该股 + 缓存/分时数据完备”时才会继续判断。

- **条件0：持仓过滤**
  - 若 `stock_code in broker.positions`，直接不买。

- **条件1：价格强于 MA5 顶部支撑**
  - 要求 `current_price >= cached['last_ma5_top_price']`。

- **条件2：当前价处于 T 日收盘价的 ±N% 区间**
  - `t_day_price_range=0.06`
  - `t_day_close*(1-0.06) <= current_price <= t_day_close*(1+0.06)`。

- **条件3：日内突破昨日实体上沿**
  - 昨日实体上沿：`yesterday_entity_top = max(yesterday_open, yesterday_close)`。
  - 要求当日分时最高价 `current_high > yesterday_entity_top`。

- **条件4：不追高（最高涨幅限制）**
  - 最高涨幅：`(current_high - yesterday_close) / yesterday_close`。
  - 要求 `< max_daily_change_rate(=0.08)`。

- **条件5：价格强于分时均价（成交额/成交量）**
  - `avg_price = sum(amount) / sum(volume)`。
  - 要求 `current_price >= avg_price`。

- **条件6：分时 MACD 底部**
  - `is_macd_bottom(get_macd(bars)) == True`。

- **条件7：动态日线 MACD 红柱且强于昨日**
  - 用分时数据构造“动态日 K”（`get_dynamic_daily_kline`），与历史日线拼接后计算 MACD。
  - 要求：
    - 今日 `macd > 0`
    - 且今日 `macd > 昨日 macd`

---

### 五、卖出信号与组合逻辑（对应 `sell_signal`）
> 说明：卖出只对持仓股生效，且必须有可用可卖数量。

- **卖出保护：当前涨停不卖出**
  - 若 `is_limit(stock_code, current_price, yesterday_close)` 为 True，直接不卖出。

#### 组合B：炸板清仓（优先级最高，对应 `_sell_combo_b_broken_limit`）
- **触发条件**
  - 日内曾触及涨停：`max(high) >= limit_up_price`
  - 且当前未封住涨停：`current_price < limit_up_price`
  - 且距离最近一次“收盘价触及涨停”的分钟数间隔 `gap >= sell_broken_limit_gap_minutes(=3)`（视作“3分钟未回封”）
- **动作**
  - 直接按 `available_volume` 清仓卖出。

#### MACD 顶点过滤门槛（组合A/C 的必要条件，对应 `_check_macd_top_gate`）
- **基础条件**
  - 分时 MACD 出现顶点：`is_macd_top(get_macd(bars)) == True`
- **通过条件（满足任意一条即可）**
  - 日内首次出现（无上一次顶点记录）
  - 当前顶点价格低于上一次顶点价格（弱势）
  - 顶背离：价格不低于上次顶点价，但本次顶点 `macd` 柱值小于上次顶点 `macd`

#### 组合A：分批止盈（对应 `_sell_combo_a_take_profit`）
- **触发条件**
  - 当前盈利：`current_price > cost_price`
  - 且满足以下任意一条：
    - 昨日最大涨幅 \(\ge\) `sell_yesterday_max_change_rate(=0.08)`
    - 昨日成交量放大：
      - 若昨日为建仓日：放大率 \(\ge\) `sell_volume_expand_rate_build_day(=0.30)`
      - 否则：放大率 \(\ge\) `sell_volume_expand_rate_normal(=0.10)`
    - 日内最大涨幅 \(\ge\) `sell_intraday_max_change_rate(=0.09)`
  - 且通过“MACD 顶点过滤门槛”
- **动作**
  - 分批卖出：`sell_volume = available_volume / remaining_batch_count`
  - 通过 `convert_to_safe_sell_volume` 转换为安全委托数量（100 整数倍）后下单。
  - 卖出后 `batch_sell_count -= 1`，并更新顶点缓存（`top_price/top_macd`）。

#### 组合C：分批止损（对应 `_sell_combo_c_stop_loss`）
- **触发条件**
  - 以 `last_ma5_top_price` 作为支撑位，当前价跌破：`current_price < last_ma5_top_price`
  - 且通过“MACD 顶点过滤门槛”
- **动作**
  - 与组合A相同的分批卖出机制（安全委托数量 + 扣减批次 + 更新顶点缓存）。

---

### 六、盘中数据更新（对应 `on_minute_end`）
- **用途**
  - 在每分钟结束时检测分时 MACD 顶点；若出现顶点，记录当下价格与 `macd` 柱值到缓存：
    - `cached[stock_code]['top_price']`
    - `cached[stock_code]['top_macd']`
- **意义**
  - 为后续卖出中的“比较上一次顶点 / 顶背离判断”提供参考点，避免单次顶点误判导致频繁卖出。

---

### 七、关键参数清单（来自 `__init__`）
- **价格区间**
  - `price_min=5.0`
  - `price_max=100.0`
- **选股条件**
  - `limit_check_days=5`：近 N 日存在涨停
  - `max_limit_board=2`：最多 N 板（首板/二板）
  - `min_days_after_limit=3`：距离 T 日至少 N 个交易日
  - `volume_check_days=20`：近 N 日最大成交量检查
  - `amplitude_check_days=20`：近 N 日振幅检查
  - `max_amplitude=0.5`：最大振幅
  - `limit_count_check_days=250`：近 N 日涨停次数统计窗口
  - `min_limit_count=6`：近 1 年涨停次数阈值
  - `daily_bars_count=260`：选股时拉取日线条数
- **买入信号**
  - `t_day_price_range=0.06`：T 日收盘价波动范围（±6%）
  - `max_daily_change_rate=0.08`：当日最高涨幅限制（<8%）
- **卖出信号**
  - `batch_sell_count=2`：分批卖出次数
  - `sell_macd_min_bars=5`：MACD 顶点/底部判定所需最少分时K线数量
  - `sell_broken_limit_gap_minutes=3`：炸板判定“3分钟未回封”
  - `sell_yesterday_max_change_rate=0.08`：昨日最大涨幅阈值
  - `sell_intraday_max_change_rate=0.09`：日内最大涨幅阈值
  - `sell_volume_expand_rate_normal=0.10`：非建仓日昨日成交量放大阈值
  - `sell_volume_expand_rate_build_day=0.30`：建仓日昨日成交量放大阈值

---

### 八、注意事项与风险提示
1. **数据依赖**
   - 选股依赖约 1 年（日线约 260 根）的历史数据以统计涨停次数。
   - 买卖依赖分时数据（至少 `sell_macd_min_bars` 根分钟K线）与盘前缓存的日线数据。
2. **“MA5 顶部支撑位”的含义**
   - 本策略使用 MA5 顶部当日的 **MA5 均线值** 作为支撑位，而非价格实体/收盘价；该支撑位更平滑，但也可能更“钝”。
3. **炸板清仓的偏保守**
   - 只要触及涨停后 3 分钟未回封就清仓，适合控制回撤，但可能会错过回封后的继续拉升。
4. **分批卖出机制**
   - 每天盘前会重置 `batch_sell_count`（默认 2），因此该分批是“日内分批”，不是跨日累计分批。
5. **日志与可观测性**
   - 代码中对关键触发点已记录日志（例如“炸板清仓/分批止盈/分批止损/选股命中”），回测/实盘建议配合日志回溯验证信号触发是否符合预期。

