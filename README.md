# MoneyDog 量化交易系统

MoneyDog 是一个基于QMT + Python的量化交易回测系。

## 🚀 功能特性

- **策略回测**: 支持历史数据回测，验证交易策略的有效性
- **技术分析**: 内置多种技术指标和图形识别算法
- **模拟交易**: 完整的模拟交易环境，包括资金管理、持仓管理、手续费计算
- **数据管理**: 支持多种数据源，包括 AKShare 和 XTQuant
- **日志系统**: 完整的日志记录和性能分析
- **配置管理**: 灵活的配置文件管理

## 📁 项目结构

```
MoneyDog/
├── main.py                 # 主程序入口
├── config.ini             # 配置文件
├── config.example.ini     # 配置文件示例
├── requirements.txt       # 依赖包列表
├── strategys/            # 策略模块
│   └── BuyOnDips.py      # 买入在低点策略
├── utils/                # 工具模块
│   ├── broker.py         # 模拟交易实现
│   ├── data.py           # 数据获取和处理
│   ├── logger.py         # 日志系统
│   └── util.py           # 通用工具函数
├── laboratory/           # 实验室模块
│   ├── custom.py         # 自定义图形识别
│   ├── singleK.py        # 单K线分析
│   └── multipleK.py      # 多K线分析
├── test/                 # 测试模块
├── logs/                 # 日志文件
├── results/             # 回测结果
└── xtquant/             # XTQuant 数据接口
```

## 🛠️ 安装配置

### 环境要求

- Python 3.6+
- Windows 系统（当前版本）

### 安装步骤

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd MoneyDog
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **配置系统**
   ```bash
   # 复制配置文件模板
   copy config.example.ini config.ini
   
   # 编辑配置文件
   notepad config.ini
   ```

### 主要依赖包

- `akshare`: 数据接口
- `pandas`: 数据处理
- `numpy`: 数值计算
- `matplotlib`: 图表绘制
- `xtquant`: 数据接口
- `openpyxl`: Excel 文件处理

## ⚙️ 配置说明

### 配置文件 (config.ini)

```ini
[LOGGING]
# 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
level = INFO

[DOWNLOAD]
# 是否需要下载历史行情数据
download_required = false
# 历史行情数据的开始时间
download_start_time = 20250101

[BACKTEST]
# 回测开始时间
backtest_start_time = 20250901
# 回测结束时间
backtest_end_time = 20250930
# 初始资金
initial_amount = 1000000
# 手续费率（双向收取）
commission_rate = 0.0001
# 最低佣金（双向收取）
min_commission = 5
# 印花税（卖出收取）
tax_rate = 0.0005
# 限制单股买入仓位方式选择(比例:"ratio"/金额:"amount")
limit_vol_type = "amount"
# 单股买入最大仓位比例
max_vol_rate = 0.05
# 单股买入最大仓位金额
max_vol_amount = 100000
```

## 🎯 核心策略

### BuyOnDips 策略

示例策略，基于以下技术分析：

1. **选股条件**:
   - 首板后的缩量盘整图形
   - 成交量逐日递减
   - 价格震荡幅度在合理区间

2. **交易信号**:
   - 买入信号：基于分时线数据的技术指标
   - 卖出信号：持仓股票的止盈止损

3. **风险控制**:
   - 单股仓位限制
   - 资金管理
   - 手续费和印花税计算

## 🚀 快速开始

### 运行回测

```bash
python main.py
```

### 查看结果

回测完成后，结果将保存在 `results/` 目录下：

- `results_YYYYMMDD_HHMMSS.xlsx`: 详细的回测结果


## 📊 输出结果

### 回测报告

- **资产概览**: 初始资金、最终资产、总收益率
- **交易统计**: 交易次数、胜率、平均收益
- **持仓分析**: 持仓股票、仓位分布
- **风险指标**: 最大回撤、夏普比率等

### 图表分析

- 资产曲线图
- 持仓分布图
- 收益分布图

## 🔧 开发指南

### 添加新策略

1. 在 `strategys/` 目录下创建新的策略文件
2. 继承基础策略类或参考 `BuyOnDips.py`
3. 实现必要的策略方法：
   - `prepare()`: 策略准备
   - `before_open()`: 开盘前处理
   - `on_minute()`: 分时线处理
   - `after_close()`: 收盘后处理

### 自定义技术指标

在 `laboratory/` 目录下添加自定义的技术分析函数：

- `singleK.py`: 单K线分析
- `multipleK.py`: 多K线分析
- `custom.py`: 自定义图形识别

### 数据接口扩展

在 `utils/data.py` 中添加新的数据获取函数，支持：

- AKShare 数据接口
- XTQuant 数据接口
- 自定义数据源

## 📝 日志系统

系统提供完整的日志记录功能：

- **日志级别**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **日志文件**: 保存在 `logs/` 目录
- **日志格式**: 包含时间戳、级别、模块、消息

## 🧪 测试

运行测试用例：

```bash
# 运行所有测试
python -m pytest test/

# 运行特定测试
python test/test_data.py
python test/test_broker.py
```


## 🤝 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## ⚠️ 免责声明

本项目仅供学习和研究使用，不构成投资建议。使用本系统进行实际交易的风险由用户自行承担。请谨慎投资，理性交易。

---

**注意**: 本系统目前仅支持 Windows 平台，使用前请确保已正确安装所有依赖包。
