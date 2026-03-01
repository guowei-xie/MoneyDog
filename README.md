## MoneyDog 量化交易系统

MoneyDog(旺财) 是一个基于 **Python + 本地 DuckDB 数据库** 的量化交易回测小系统，采用策略基类架构，支持灵活的策略开发与配置。

### 🚀 功能特性

- **Web 控制台**: 提供基于 FastAPI 的浏览器前端（`web/server.py`），支持策略选择、参数配置、一键启动/中止回测与历史回测管理
- **交互式配置界面**: 提供终端应用入口 (`app.py`)，支持可视化配置参数，无需手动编辑配置文件
- **策略基类架构**: 提供 `BaseStrategy` 基类，简化策略开发流程
- **策略可配置**: 通过配置文件切换策略，无需修改代码
- **策略回测**: 按交易日逐日回放，支持分钟级分时回测
- **多线程选股**: 回测前一次性加载日线全量到内存，按交易日多线程预选股并缓存，遍历交易日时直接取用，提升回测效率
- **技术分析**: 内置多种 K 线、均线、量能、MACD 等技术指标与图形识别算法
- **模拟交易**: 支持资金管理、持仓管理、佣金与印花税精细计算
- **数据管理**: 使用 DuckDB 本地库 (`data/stock.duckdb`) 存储日线与分钟线行情
- **结果分析**: 自动导出交易记录、账户曲线与分析结果 Excel
- **日志系统**: 全量记录回测过程，便于诊断与调优

---

## 📁 项目结构（当前版本）

```text
MoneyDog/
├── app.py                 # 终端应用入口，交互式配置界面
├── main.py                # 主程序入口，运行回测
├── config.ini             # 实际配置文件
├── config.example.ini     # 配置文件示例
├── requirements.txt       # 依赖包列表
├── data/
│   └── stock.duckdb       # 行情数据 DuckDB 库（需预先准备）
├── web/                  # Web 前端与 API 服务
│   ├── server.py         # FastAPI 应用入口（浏览器控制台）
│   ├── templates/        # Web 界面模板（单页控制台）
│   └── __init__.py
├── strategys/             # 策略模块
│   ├── BaseStrategy.py    # 策略基类，提供通用框架
│   └── *.py               # 具体策略实现
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
- 通过自有脚本将日线与 1 分钟线行情写入对应表（如 `stock_list`、`daily_1day`、`daily_1min`）

当前代码假定 DuckDB 中至少存在：

- `stock_list`：包含 `code` 字段，用于构建主板股票池
- `daily_1day`：日线行情，包含 `code, time, open, high, low, close, volume, amount`
- `daily_1min`：1 分钟行情，字段同上

---

## ⚙️ 配置说明（config.ini 当前字段）

> 💡 **提示**: 推荐使用 `python app.py` 启动交互式配置界面，无需手动编辑配置文件。以下为配置文件字段说明，供参考。

### 日志与数据

```ini
[LOGGING]
# 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
level = INFO

[DATA]
# DuckDB 行情数据库路径
data_path = data/stock.duckdb
```

### 策略配置

```ini
[STRATEGY]
# 策略模块名（策略文件名，不含.py后缀）
strategy_module = N_Pattern_Bottom
# 策略类名（策略类名称）
strategy_class = NPatternBottom
```

> 通过修改 `[STRATEGY]` 配置段即可切换不同策略，无需修改代码。

### 回测参数

```ini
[BACKTEST]
# 冗余日志开关:
# - verbose = False: 简约模式（显示回测/选股进度条，不显示部分冗余信息日志）
# - verbose = True : 冗余模式（显示部分冗余信息日志，不显示回测/选股进度条）
verbose = False
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

# 选股是否使用多线程：True=多线程（生产），False=单线程（便于开发调试）
batch_stock_selection_use_threads = True
# 多线程选股时的线程数（仅 use_threads=True 时生效，0=自动）
batch_stock_selection_threads = 0
```

---

## 🚀 快速开始

### 方式一：使用交互式配置界面（推荐）

运行终端应用入口，通过可视化界面配置参数并运行：

```bash
python app.py
```

应用提供以下功能：

- **查看配置**: 查看当前所有配置段的参数值
- **编辑配置**: 按配置段分组编辑（日志、数据、策略、回测），支持连续编辑多个配置项
- **运行策略**: 显示配置摘要后确认运行，自动加载策略并开始回测
- **默认配置**: 如果用户未进行配置，则自动使用 `config.ini` 中的默认配置

所有配置修改会自动保存到 `config.ini` 文件中。

### 方式二：直接运行主程序

1. **配置策略**

   在 `config.ini` 的 `[STRATEGY]` 段中配置要使用的策略：

   ```ini
   [STRATEGY]
   strategy_module = N_Pattern_Bottom
   strategy_class = NPatternBottom
   ```

2. **运行回测**

   确保 `config.ini` 与 `data/stock.duckdb` 准备妥当后，在项目根目录执行：

   ```bash
   python main.py
   ```

   系统会自动根据配置文件加载对应策略并开始回测。

   日志会输出到控制台及 `logs/MoneyDog_YYYY-MM-DD.log`。

### 方式三：使用 Web 控制台（浏览器前端）

在项目根目录启动 FastAPI 服务：

```bash
python -m web.server
# 或使用 uvicorn（自定义 host/port）
uvicorn web.server:app --host 127.0.0.1 --port 8000 --reload
```

然后在浏览器中访问：

- `http://127.0.0.1:8000`

Web 控制台提供：

- 左侧：策略模块/类选择、回测时间区间、初始资金/费用、仓位与多线程参数配置，一键开始/中止回测
- 右侧上半部分：当前回测的账户指标卡片 + 账户收益与仓位曲线图
- 右侧下半部分：历史回测列表（点击某行可查看结果，支持删除记录、打开对应分析 Excel）

### 查看结果

#### 方式一：在 Web 控制台中查看

- “本次回测结果”中会展示：
  - 账户层指标（收益率、最大回撤、夏普、最大持仓数、最大仓位、空仓天数等）
  - 账户收益与仓位曲线图
  - 账户分析结果摘要、个股分析结果摘要（与日志中输出内容一致）
- “历史回测”中：
  - 点击某一行可回看对应回测的曲线与指标
  - “记录”按钮可直接下载该次回测的主要分析 Excel
  - “删除”按钮只删除历史记录索引，不删除实际结果文件

#### 方式二：直接查看结果文件

回测完成后，`results/` 目录下会生成若干 Excel/PNG 文件，例如：

- `original_transactions_YYYYMMDD_HHMMSS.xlsx`：原始逐笔交易与持仓变动
- `position_and_account_changes_YYYYMMDD_HHMMSS.xlsx`：每日账户与持仓统计
- `analyze_transactions_YYYYMMDD_HHMMSS.xlsx`：交易统计分析结果（由 `laboratory/analyze.py` 生成）
- `account_curve_YYYYMMDD_HHMMSS.png`：账户收益与仓位曲线图

---

## 📊 典型分析指标

分析模块会基于交易记录与账户曲线，计算并输出（具体以代码实现为准）：

- **资金与收益**: 初始资金、期末总资产、总收益率
- **交易统计**: 交易次数、完成闭环股票数量、胜率、平均盈利率与亏损率
- **仓位与风险**: 每日持仓数量、最大持仓数、账户资产曲线及最大回撤

（如需更多因子/图表，可在 `laboratory/analyze.py` 中自行扩展。）

---

## 🔧 开发与扩展指南

### 策略基类运行流程

`BaseStrategy` 基类提供了完整的回测框架，运行流程如下：

```mermaid
flowchart TD
    A[开始运行] --> B[prepare 准备阶段]
    B --> B1[获取交易日期列表]
    B1 --> B2[获取股票池]
    B2 --> B3[加载日线全量到内存]
    B3 --> B4[多线程预选股并缓存]
    B4 --> C{遍历交易日历}
    
    C --> D[before_open 开盘前]
    D --> D1[清理持仓/解锁]
    D1 --> D2[获取持仓列表]
    D2 --> D3[取用预选股缓存或选股]
    D3 --> D4[set_cached<br/>子类实现: 缓存指标数据]
    D4 --> D5[生成分时快照]
    D5 --> D6{是否有股票?}
    
    D6 -->|否| E[after_close 收盘后]
    D6 -->|是| F{遍历分时快照}
    
    F --> G[on_minute 盘中运行]
    G --> G1{股票类型?}
    G1 -->|自选股| G2[buy_signal<br/>子类实现: 买入信号]
    G1 -->|持仓股| G3[sell_signal<br/>子类实现: 卖出信号]
    G2 --> G4{有信号?}
    G3 --> G4
    G4 -->|是| G5[执行交易]
    G4 -->|否| F
    G5 --> F
    
    F -->|完成| E
    E --> E1[更新持仓信息]
    E1 --> E2[记录账户变化]
    E2 --> C
    
    C -->|所有交易日完成| H[end_of_backtest 回测结束]
    H --> H1[导出交易记录]
    H1 --> H2[导出账户变化]
    H2 --> H3[分析交易结果]
    H3 --> I[结束]
```

#### 流程说明

**准备阶段（prepare）**
- 获取交易日期列表：根据配置的回测时间区间生成交易日历
- 获取股票池：默认使用主板股票池，子类可重写 `_get_stock_list()` 方法
- 加载日线全量到内存：一次性从 DuckDB 读取日线行情至 `_daily_bars_cache`，供选股只读
- 预选股：按交易日调用子类 `get_selected_stock_list(trade_date)`，结果写入 `_selected_stock_by_date`，带进度条。是否多线程由配置 `batch_stock_selection_use_threads` 控制（False=单线程，便于开发调试）；为 True 时线程数由 `batch_stock_selection_threads` 控制（0 为自动）

**每日运行循环**
- **开盘前（before_open）**：
  - 清理持仓：清除 volume 为 0 的持仓，解锁昨日被锁定的持仓
  - 获取持仓列表：当前持有的股票（预卖出）
  - 获取自选列表：优先从预选股缓存 `_selected_stock_by_date[trade_date]` 取用，若无缓存则调用子类 `get_selected_stock_list(trade_date)`
  - 缓存数据：调用子类的 `set_cached()` 方法计算并缓存技术指标
  - 生成分时快照：为当日回测准备分钟级行情数据

- **盘中运行（on_minute）**：
  - 钩子：遍历每只股票的分钟数据前调用 `on_minute_start()`，处理完信号与交易后调用 `on_minute_end()`，便于在信号判断前后做额外准备或收尾
  - 遍历每分钟的快照数据
  - 对于自选股：调用子类的 `buy_signal()` 方法判断买入信号
  - 对于持仓股：调用子类的 `sell_signal()` 方法判断卖出信号
  - 如有信号，执行交易（买入/卖出）

- **收盘后（after_close）**：
  - 更新持仓信息：使用最后一个分时快照更新持仓最新价
  - 记录账户变化：记录当日账户与持仓变化

**回测结束（end_of_backtest）**
- 导出交易记录和账户变化数据到 Excel
- 调用分析模块对交易结果进行统计分析

> **注意**：标有"子类实现"的方法需要由策略开发者实现，其他流程由基类自动处理。

### 基于策略基类开发新策略

推荐使用策略基类 `BaseStrategy` 开发新策略，可以大幅简化开发流程。

#### 步骤1：创建策略文件

在 `strategys/` 目录下创建新的策略文件，例如 `MyStrategy.py`：

```python
from strategys.BaseStrategy import BaseStrategy
from typing import List, Dict, Optional
import pandas as pd

class MyStrategy(BaseStrategy):
    """
    我的策略
    """
    
    def __init__(self):
        """
        初始化策略
        """
        super().__init__()
        # 添加策略特定参数
        self.price_min = 5.0
        self.price_max = 60.0
    
    def get_selected_stock_list(self, trade_date: str) -> List[str]:
        """
        获取自选股票列表（预买入）
        子类必须实现此方法
        """
        # 实现选股逻辑
        pass
    
    def set_cached(self, trade_date: str) -> bool:
        """
        缓存盘前数据（备用于盘中运行）
        子类必须实现此方法
        """
        # 实现数据缓存逻辑
        pass
    
    def buy_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        买入信号生成
        子类必须实现此方法
        """
        # 实现买入信号逻辑
        pass
    
    def sell_signal(self, stock_code: str, bars: pd.DataFrame) -> Optional[Dict]:
        """
        卖出信号生成
        子类必须实现此方法
        """
        # 实现卖出信号逻辑
        pass
```

#### 步骤2：实现四个核心方法（必选）+ 两个盘中钩子（可选）

基类要求实现以下四个抽象方法：

1. **`get_selected_stock_list(trade_date)`**：获取自选股票列表（预买入）
   - 根据选股条件筛选股票，返回股票代码列表
   - 选股阶段应使用 `self.get_daily_bars_for_selection(trade_date, count)` 获取日线数据，以走内存缓存、配合多线程预选股

2. **`set_cached(trade_date)`**：缓存盘前数据
   - 计算并缓存技术指标
   - 存储到 `self.cached[stock_code]` 字典中

3. **`buy_signal(stock_code, bars)`**：买入信号生成
   - 根据分时K线数据判断买入条件
   - 返回交易信号字典或 `None`

4. **`sell_signal(stock_code, bars)`**：卖出信号生成
   - 根据分时K线数据判断卖出条件
   - 返回交易信号字典或 `None`

可选的盘中钩子（非抽象方法，可按需重写）：

- **`on_minute_start(stock_code, bars)`**：每只股票在当分钟信号判断前触发，可用于预处理或缓存最新指标
- **`on_minute_end(stock_code, bars)`**：每只股票在当分钟处理完成后触发，可用于记录调试信息或复位状态

#### 步骤3：配置策略

在 `config.ini` 中添加策略配置：

```ini
[STRATEGY]
strategy_module = MyStrategy
strategy_class = MyStrategy
```

#### 步骤4：运行回测

直接运行 `main.py`，系统会自动加载配置的策略：

```bash
python main.py
```

#### 基类提供的功能

`BaseStrategy` 基类已经实现了以下功能，无需重复开发：

- ✅ 策略运行主流程（`run()`）
- ✅ 交易日历获取与遍历
- ✅ 股票池管理
- ✅ 开盘前/收盘后处理
- ✅ 分时快照生成与遍历
- ✅ 持仓管理
- ✅ 交易执行
- ✅ 回测结果导出与分析

#### 参考示例

可以参考 `strategys/` 目录下的现有策略实现了解完整的开发示例。

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
