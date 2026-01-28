# 分析报告目录

本目录用于存放各种分析报告脚本和生成的结果。

## 目录结构

```
report/
├── README.md                          # 本说明文件
├── limit_up_distribution/             # 涨停次数分布分析报告
│   ├── script.py                      # 分析脚本
│   └── results/                       # 生成的结果文件
│       ├── limit_up_distribution_*.png
│       ├── limit_up_detail_*.csv
│       └── limit_up_summary_*.txt
└── [其他报告目录]/                    # 未来添加的其他分析报告
    ├── script.py
    └── results/
```

## 设计原则

1. **每个报告一个独立目录**：便于管理和维护
2. **脚本与结果分离**：脚本放在报告目录根下，结果统一放在 `results/` 子目录
3. **命名规范**：报告目录使用小写字母和下划线，如 `limit_up_distribution`

## 报告列表

### 1. 涨停次数分布分析报告

**目录**: `limit_up_distribution/`

**脚本**: `limit_up_distribution/script.py`

**功能**: 
- 获取主板股票列表及数据（数据范围同配置文件）
- 计算所有股票在该范围内的涨停次数
- 绘制分布图，探知"有涨停的股票，在范围内大部分会涨停多少次"

**使用方法**:
```bash
# 在项目根目录下运行
python report/limit_up_distribution/script.py
```

**输出文件** (保存在 `limit_up_distribution/results/` 目录):
- `limit_up_distribution_{start_time}_{end_time}.png` - 分布图表
- `limit_up_detail_{start_time}_{end_time}.csv` - 详细数据（包含每只有涨停的股票及其涨停次数）
- `limit_up_summary_{start_time}_{end_time}.txt` - 统计摘要

**数据范围**: 从配置文件 `config.ini` 的 `BACKTEST` 部分读取 `backtest_start_time` 和 `backtest_end_time`

**注意事项**:
- 需要确保数据库文件路径正确且可访问（配置文件中的 `data_path`）
- 需要确保有足够的数据覆盖指定时间范围

## 添加新报告

添加新分析报告时，请遵循以下步骤：

1. 在 `report/` 目录下创建新的报告目录，使用小写字母和下划线命名
2. 在新目录下创建 `script.py` 文件
3. 在脚本中设置结果保存路径为 `{脚本目录}/results/`
4. 在本 README 中添加新报告的说明

示例目录结构：
```
report/
└── new_report_name/
    ├── script.py
    └── results/
```
