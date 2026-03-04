# 突破前高涨停打板策略（与当前代码实现保持同步说明）

## 一、整体思路

- **选股阶段（日线）**  
  - 先借未来函数用 T+1 日最高涨幅缩池，再仅对缩池结果取 90 日线做实体前高筛选，减少行情数据量与内存占用。  
  - 条件包括：T+1 最高涨幅达标、T 日收盘在前高下方一定区间、T 日收盘不高于前高、T~T-n 区间涨幅不超限。  
  - 使用主板股票池（由基类 `_get_stock_list` 决定）。  
- **买入阶段（分时）**  
  - 涨幅接近涨停 + 当日最低或昨日收盘低于前高 + 当前分时价高于前高；且开盘价涨幅、当前分时之前的日内最高涨幅均不超过“接近涨停”阈值。  
  - 所有买入条件必须同时满足。  
- **卖出阶段（分时）**  
  - 当前涨停则不卖；炸板则立即清仓；否则按 MACD 首个顶或顶背离分批卖出。  

---

## 二、选股条件（对应 `get_selected_stock_list`）

选股分两步：先用 T+1 数据缩池，再对缩池结果做日线条件筛选。

### 第一步：未来函数缩池（仅用于减少预选股数量与内存）

- **条件1（未来函数）**  
  - T+1 交易日最高价相对 T 日收盘的涨幅 ≥ `limit_near_pct`（默认 9.5%）。  
  - 即 `(T+1 日最高价 - T 日收盘) / T 日收盘 >= limit_near_pct`。  
  - 与买入“接近涨停”阈值一致，不改变回测结果，仅缩小后续 90 日线取数范围。  

### 第二步：对缩池结果取 90 日线并筛选

- **条件2：实体前高与 T 日收盘区间**  
  - **前高定义**：近 `lookback_days` 日（默认 90 日）内，**不含 T 日**，每根 K 线取 `max(开盘价, 收盘价)`，再取全期最大，记为“前高”`entity_high`。  
  - **阈值**：`threshold = entity_high * (1 - margin_pct)`，默认 `margin_pct = 0.10` 即前高下沿 -10%。  
  - 要求：**T 日收盘价 > threshold**，且 **T 日收盘价 ≤ entity_high**（即 T 日收盘不能高于前高）。  

- **条件3：T~T-n 日区间振幅**  
  - 区间振幅 = `区间最高价 / 区间最低价 - 1`（区间为 T~T-n 共 `interval_days + 1` 个交易日）。  
  - 要求：区间振幅 **不能大于** `interval_max_amplitude_pct`（默认 25%）。  
  - `interval_days` 默认 10，即 T 到 T-n 共 11 个交易日。  
  - 需至少 `interval_days + 1` 根 K 线且区间最低价 > 0 才参与本条件，否则该股跳过。  

- **条件4：近 interval_days 日内涨停次数上限**  
  - 近 `interval_days` 个交易日（默认 10 日）内涨停次数不能超过 `max_limit_count_in_recent_days`（默认 2 次）。  
  - 使用日线 `close`、`preClose` 与 `is_limit(stock_code, close, preClose)` 逐日判断并计数。  

- **条件5：近1年涨停次数**  
  - 近 `limit_count_check_days` 日（默认 250，约 1 年）内涨停次数 ≥ `min_limit_count`（默认 5）。  
  - 实现方式与 N_Pattern_Breakout_V2 一致：在区间内逐日用 `is_limit` 判断并计数。  
  - 若日线不足 `limit_count_check_days` 条，则在已有数据范围内统计。  

---

## 三、盘前缓存（对应 `set_cached`）

- **昨日收盘价** `pre_close`：T 日收盘价，供次日分时作为“昨收”使用。  
- **前高价格线** `prev_high_price`：与选股一致，近 N 日实体最高价**不含 T 日**（用 T 日前数据计算）。  
- **卖出相关**：`batch_sell_count`（每日盘前重置）、`top_price`、`top_macd`（分时 MACD 顶点记录，用于顶背离判断）。  

---

## 四、买入信号（全部满足，对应 `buy_signal`）

- **前置**  
  - 未持仓该股；`bars` 非空；该股在 `cached` 中且 `pre_close > 0`。  

- **开盘价与“当前分时前”涨幅约束**  
  - **开盘价涨幅**：当日开盘价 `day_open <= pre_close * (1 + limit_near_pct)`，即开盘价涨幅不能大于 `limit_near_pct`。  
  - **当前分时之前**：在**当前这根分时 K 之前**，所有分时 K 的最高价未超过 `pre_close * (1 + limit_near_pct)`。即此前未出现过涨幅大于 `limit_near_pct` 的情况。  

- **信号1：当前涨幅接近涨停**  
  - 当前分时收盘价 / 昨日收盘价 ≥ `1 + limit_near_pct`（默认 ≥ 9.5%）。  

- **信号2：当日最低或昨日收盘低于前高**  
  - 以下至少满足其一：当日分时最低价 < 前高价格线，或昨日收盘价 < 前高价格线。  

- **信号3：当前分时价高于前高**  
  - 当前分时收盘价 > 前高价格线 `prev_high_price`。  

满足上述全部条件且资金可用时，生成买入信号；否则返回 `None`。  

---

## 五、卖出信号与组合逻辑（对应 `sell_signal`）

### 卖出屏蔽

- **当前涨停不卖**：若当前分时价格已涨停（`is_limit(stock_code, current_price, yesterday_close)` 为 True），直接返回 `None`，不产生任何卖出信号。  

### 卖出组合（按优先级）

- **组合1：炸板清仓**  
  - 当日曾触及涨停价（分时最高价 ≥ 涨停价），且当前价 < 涨停价。  
  - 且距离**最近一次封板**（收盘价 ≥ 涨停价的那根 K）已超过 `sell_broken_limit_gap_minutes`（默认 3 分钟）未回封，视为炸板。  
  - 触发时按**全部可用数量**清仓，`desc` 为“止盈（炸板）”。  

- **组合2：MACD 首个顶或顶背离分批卖出**  
  - 分时 MACD 出现顶点（`is_macd_top`），且满足以下**任一**：  
    - 日内首次出现（无上一顶点记录）；  
    - 当前价低于上一顶点价；  
    - 顶背离：当前价 ≥ 上一顶点价，但当前 MACD 柱值 < 上一顶点 MACD 值。  
  - 触发时按**剩余分批次数**计算本次卖出量（100 整数倍），扣减一次 `batch_sell_count`，并更新顶点缓存；`desc` 为“止盈（MACD顶/顶背离）”。  

### 分钟结束更新（`on_minute_end`）

- 若当前分时出现 MACD 顶点，则更新 `top_price`、`top_macd`，供下一根 K 判断顶背离使用。  

---

## 六、可配置参数（`__init__`）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `lookback_days` | 90 | 选股与缓存所用日线回溯天数。 |
| `margin_pct` | 0.10 | 前高下沿比例，阈值 = 前高 × (1 - margin_pct)。 |
| `limit_near_pct` | 0.095 | “接近涨停”涨幅阈值；选股未来函数与买入共用。 |
| `batch_sell_count` | 2 | MACD 顶/顶背离触发时的分批卖出次数。 |
| `sell_macd_min_bars` | 5 | 分时 MACD 顶点判定所需最少 K 线数量。 |
| `sell_broken_limit_gap_minutes` | 3 | 炸板判定：距最近封板超过该分钟数未回封则清仓。 |
| `interval_days` | 10 | T~T-n 区间长度 n（交易日数）；也用于“近 n 日涨停次数”统计窗口。 |
| `max_limit_count_in_recent_days` | 2 | 近 interval_days 日内最多允许的涨停次数。 |
| `interval_max_amplitude_pct` | 0.25 | T~T-n 日区间振幅上限（最高价/最低价-1，25%）。 |
| `limit_count_check_days` | 250 | 近1年涨停次数统计区间（约 1 年交易日）。 |
| `min_limit_count` | 5 | 近1年涨停次数下限。 |

---

## 七、与代码文件对应关系

- 策略类与文件：`strategys/BreakPrevHighLimitUp.py` → `BreakPrevHighLimitUp`。  
- 选股：`get_selected_stock_list`。  
- 盘前缓存：`set_cached`。  
- 买入：`buy_signal`。  
- 卖出：`sell_signal`；炸板清仓 `_sell_broken_limit`；MACD 分批 `_sell_batch_on_macd_top`；顶点过滤 `_check_macd_top_gate`；顶点缓存更新 `_update_top_cache`、`on_minute_end`。  

若代码有增删改，请同步更新本说明。
