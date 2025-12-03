## MoneyDog 量化交易系统

MoneyDog 是一个基于 **Python + 本地 DuckDB 数据库** 的量化交易回测小系统，目前内置一套「首板缩量盘整 + 分时择时」示例策略 `BuyOnDips`。

### 🚀 功能特性

- **策略回测**: 按交易日逐日回放，支持分钟级分时回测
- **技术分析**: 内置多种 K 线、均线、量能、MACD 等技术指标与图形识别算法
- **模拟交易**: 支持资金管理、持仓管理、佣金与印花税精细计算
- **数据管理**: 使用 DuckDB 本地库 (`data/stock.duckdb`) 存储日线与分钟线行情
- **结果分析**: 自动导出交易记录、账户曲线与分析结果 Excel
- **日志系统**: 全量记录回测过程，便于诊断与调优

---

## 📁 项目结构（当前版本）

```text
MoneyDog/
├── main.py                # 主程序入口，运行回测
├── config.ini             # 实际配置文件
├── config.example.ini     # 配置文件示例
├── requirements.txt       # 依赖包列表
├── data/
│   └── stock.duckdb       # 行情数据 DuckDB 库（需预先准备）
├── strategys/             # 策略模块
│   └── BuyOnDips.py       # 买入在低点示例策略
├── utils/                 # 工具与基础设施模块
│   ├── broker.py          # 模拟交易撮合与资金管理
│   ├── data.py            # 从 DuckDB 读取行情、交易日历等
│   ├── duckdb.py          # DuckDB 连接与封装
│   ├── logger.py          # 日志系统封装
│   └── util.py            # 通用工具函数（时间转换、快照生成等）
├── laboratory/            # 实验室：技术指标与图形识别
│   ├── analyze.py         # 交易与账户数据分析、生成统计报表
│   ├── custom.py          # 自定义图形识别逻辑
│   ├── singleK.py         # 单 K 线形态分析
│   └── multipleK.py       # 多 K 线、量价配合分析
├── test/                  # 单元测试
├── logs/                  # 运行日志（按日期滚动）
└── results/               # 回测输出结果（Excel）
```

> 说明：历史版本中曾依赖 QMT / XTQuant，目前代码以本地 DuckDB + AKShare 为主，相关 QMT/XTQuant 目录已移除。

---

## 🛠️ 安装与环境

### 环境要求

- **Python** ≥ 3.8
- 推荐在 **Windows** 环境下运行（日志、路径等默认按 Windows 习惯编写）

### 安装步骤

1. **克隆项目**

   ```bash
   git clone <repository-url>
   cd MoneyDog
   ```

2. **创建虚拟环境（推荐）**

   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # 或 source venv/bin/activate  # macOS / Linux
   ```

3. **安装依赖**

   ```bash
   pip install -r requirements.txt
   ```

4. **准备配置文件**

   Windows：

   ```bash
   copy config.example.ini config.ini
   notepad config.ini
   ```

   macOS / Linux：

   ```bash
   cp config.example.ini config.ini
   nano config.ini  # 或任意编辑器
   ```

5. **准备 DuckDB 数据库**

- 在 `config.ini` 中指定 DuckDB 路径（默认 `data/stock.duckdb`）
- 通过自有脚本 / Notebook / 未来的数据下载模块，将日线与 1 分钟线行情写入对应表（如 `stock_list`、`daily_1day`、`daily_1min`）

当前代码假定 DuckDB 中至少存在：

- `stock_list`：包含 `code` 字段，用于构建主板股票池
- `daily_1day`：日线行情，包含 `code, time, open, high, low, close, volume, amount`
- `daily_1min`：1 分钟行情，字段同上

---

## ⚙️ 配置说明（config.ini 当前字段）

### 日志与数据

```ini
[LOGGING]
# 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
level = INFO

[DATA]
# DuckDB 行情数据库路径
data_path = data/stock.duckdb
```

> 历史版本中的 `[DOWNLOAD]` 段已经注释掉，当前示例策略直接从本地 DuckDB 读取数据。

### 回测参数

```ini
[BACKTEST]
# 回测开始/结束时间（数字日期）
backtest_start_time = 20250901
backtest_end_time   = 20250930

# 初始资金
initial_amount = 1000000

# 手续费率（双向收取）
commission_rate = 0.0001
# 最低佣金（双向收取）
min_commission = 5
# 印花税（卖出收取）
tax_rate = 0.0005

# 单股仓位控制方式: 'ratio' 按总资产比例 / 'amount' 按固定金额
limit_vol_type = amount
# 当 limit_vol_type = ratio 时生效（如 0.05 表示单股不超过总资产 5%）
max_vol_rate = 0.05
# 当 limit_vol_type = amount 时生效（如 100000 表示单股最多 10 万）
max_vol_amount = 100000
```

---

## 🎯 内置示例策略：BuyOnDips

`strategys/BuyOnDips.py` 实现了一个「首板缩量盘整 + 分时择时买入」的示例策略，大致逻辑如下：

1. **准备阶段 `prepare()`**
   - 从 AKShare 获取交易日历（`utils.data.get_trade_calendar`）
   - 从 DuckDB 中读取主板股票池（`get_stock_list_in_main_board`）
   - 根据回测时间区间构建回测日期序列

2. **开盘前 `before_open(trade_date)`**
   - 盘前清理与解锁持仓（`Broker.clean_position` / `unlock_position`）
   - 生成待卖出列表（当前持仓）
   - 通过 `is_limit_board_after_volume_consolidation` 等条件筛选自选股（预买入池）
   - 为当日回测构造分钟级快照数据（`generate_minute_snapshot`）

3. **盘中 `on_minute(snapshot)`**
   - 对每分钟快照逐股计算买卖信号：
     - `_buy_signal`：动态 MA5 / MA10、首板涨停价、价格区间等条件
     - `_sell_signal_*`：动态 MA10 跌破、放量、昨日涨停、上板失败、MACD 顶点、炸板等
   - 调用 `Broker.buy` / `Broker.sell` 执行虚拟撮合、记录交易与资金变动

4. **收盘后 `after_close(trade_date)`**
   - 使用当日最后一个分钟快照更新持仓最新价
   - 记录账户与持仓变化（`record_position_and_account_change`）

5. **回测结束 `end_of_backtest()`**
   - 导出交易记录与账户曲线 Excel
   - 调用 `laboratory.analyze` 对交易结果进行统计分析

---

## 🚀 快速开始

### 运行回测

确保 `config.ini` 与 `data/stock.duckdb` 准备妥当后，在项目根目录执行：

```bash
python main.py
```

日志会输出到控制台及 `logs/MoneyDog_YYYY-MM-DD.log`。

### 查看结果

回测完成后，`results/` 目录下会生成若干 Excel 文件，例如：

- `original_transactions_YYYYMMDD_HHMMSS.xlsx`：原始逐笔交易与持仓变动
- `position_and_account_changes_YYYYMMDD_HHMMSS.xlsx`：每日账户与持仓统计
- `analyze_transactions_YYYYMMDD_HHMMSS.xlsx`：交易统计分析结果（由 `laboratory/analyze.py` 生成）

---

## 📊 典型分析指标

分析模块会基于交易记录与账户曲线，计算并输出（具体以代码实现为准）：

- **资金与收益**: 初始资金、期末总资产、总收益率
- **交易统计**: 交易次数、完成闭环股票数量、胜率、平均盈利率与亏损率
- **仓位与风险**: 每日持仓数量、最大持仓数、账户资产曲线及最大回撤

（如需更多因子/图表，可在 `laboratory/analyze.py` 中自行扩展。）

---

## 🔧 开发与扩展指南

### 添加新策略

1. 在 `strategys/` 目录下新增一个策略文件，例如 `MyStrategy.py`
2. 参考 `BuyOnDips` 的结构，实现以下核心方法：
   - `prepare()`：回测前准备（交易日历、股票池、缓存因子等）
   - `before_open(trade_date)`：单日开盘前逻辑
   - `on_minute(snapshot)`：分钟级行情驱动的买卖信号
   - `after_close(trade_date)`：单日收盘后处理
   - `end_of_backtest()`：回测结束后的汇总与导出
3. 在 `main.py` 中替换为自己的策略类：

   ```python
   from strategys.MyStrategy import MyStrategy

   if __name__ == "__main__":
       strategy = MyStrategy()
       strategy.run()
   ```

### 扩展技术指标与形态识别

- 在 `laboratory/singleK.py` 中扩展单 K 线形态
- 在 `laboratory/multipleK.py` 中扩展多 K 线、均线、量能等组合信号
- 在 `laboratory/custom.py` 中实现更复杂的图形或板块级逻辑

### 扩展数据接口

- `utils/data.py` 中目前主要通过 DuckDB 读取已经准备好的行情数据
- 可以：
  - 增加从 AKShare 直接获取数据并写入 DuckDB 的辅助函数
  - 接入其他数据源（如本地 CSV/Parquet 或第三方行情接口），统一写入 DuckDB

---

## 📝 日志系统

日志由 `utils/logger.py` 统一管理：

- **日志级别**: DEBUG / INFO / WARNING / ERROR / CRITICAL（由 `[LOGGING]` 段配置）
- **输出位置**: 控制台 + `logs/MoneyDog_YYYY-MM-DD.log`
- **内容**: 时间戳、级别、模块名、具体消息（含策略运行进度与关键信号）

---

## 🧪 测试

项目自带若干基础测试，可用于验证数据接口与关键工具函数：

```bash
# 运行所有测试
python -m pytest test/

# 运行特定测试
python test/test_data.py
python test/test_multipleK.py
python test/test_util.py
python test/test_logger.py
```

---

## 🤝 贡献说明

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/MyFeature`
3. 提交改动：`git commit -m "feat: add MyFeature"`
4. 推送到远程：`git push origin feature/MyFeature`
5. 提交 Pull Request 并简要说明改动内容与使用方式

---

## ⚠️ 免责声明

本项目仅供个人学习与研究使用，不构成任何投资建议。  
如将本系统用于实盘或仿真交易，由此产生的任何收益或损失由使用者自行承担，请务必独立判断、谨慎决策。
