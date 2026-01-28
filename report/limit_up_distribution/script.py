"""
涨停次数分布分析报告
分析主板股票在指定时间范围内的涨停次数分布情况
"""

import sys
import os

# 添加项目根目录到Python路径
# 脚本现在在 report/limit_up_distribution/ 目录下，需要向上两级到项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

import configparser
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
from collections import Counter
from utils.data import get_stock_list_in_main_board, get_daily_bars
from utils.logger import info, error, warning
from laboratory.singleK import is_limit
from tqdm import tqdm

# 设置中文字体
matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False


def load_config():
    """
    加载配置文件
    Returns:
        config: 配置对象
    """
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    return config


def calculate_limit_up_count(stock_code: str, daily_bars: pd.DataFrame) -> int:
    """
    计算股票在数据范围内的涨停次数
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
    Returns:
        int: 涨停次数
    """
    if daily_bars.empty or 'preClose' not in daily_bars.columns:
        return 0
    
    limit_up_count = 0
    for _, row in daily_bars.iterrows():
        if pd.isna(row.get('preClose')) or pd.isna(row.get('close')):
            continue
        if is_limit(stock_code, row['close'], row['preClose'], limit_type='up'):
            limit_up_count += 1
    
    return limit_up_count


def generate_report():
    """
    生成涨停次数分布分析报告
    """
    info("开始生成涨停次数分布分析报告")
    
    # 加载配置
    config = load_config()
    start_time = config.get('BACKTEST', 'backtest_start_time')
    end_time = config.get('BACKTEST', 'backtest_end_time')
    
    info(f"数据范围: {start_time} 至 {end_time}")
    
    # 获取主板股票列表
    info("正在获取主板股票列表...")
    try:
        stock_list = get_stock_list_in_main_board()
        info(f"获取到 {len(stock_list)} 只主板股票")
    except Exception as e:
        error(f"获取主板股票列表失败: {e}")
        return
    
    # 获取所有股票的日K数据
    info("正在获取股票日K数据...")
    try:
        daily_bars_dict = get_daily_bars(
            stock_list=stock_list,
            period='1d',
            start_time=start_time,
            end_time=end_time,
            add_preclose=True
        )
        info(f"成功获取 {len(daily_bars_dict)} 只股票的数据")
    except Exception as e:
        error(f"获取股票数据失败: {e}")
        return
    
    # 计算每只股票的涨停次数
    info("正在计算涨停次数...")
    limit_up_counts = []
    stocks_with_limit = []  # 记录有涨停的股票及其次数
    
    for stock_code, daily_bars in tqdm(daily_bars_dict.items(), desc="计算涨停次数"):
        count = calculate_limit_up_count(stock_code, daily_bars)
        limit_up_counts.append(count)
        if count > 0:
            stocks_with_limit.append({'stock_code': stock_code, 'limit_count': count})
    
    # 统计分布
    counter = Counter(limit_up_counts)
    total_stocks = len(limit_up_counts)
    stocks_with_limit_count = len(stocks_with_limit)
    stocks_without_limit = total_stocks - stocks_with_limit_count
    
    info(f"统计完成:")
    info(f"  总股票数: {total_stocks}")
    info(f"  有涨停的股票数: {stocks_with_limit_count}")
    info(f"  无涨停的股票数: {stocks_without_limit}")
    
    # 只统计有涨停的股票的分布
    limit_counts_only = [item['limit_count'] for item in stocks_with_limit]
    if not limit_counts_only:
        warning("没有找到有涨停的股票")
        return
    
    counter_with_limit = Counter(limit_counts_only)
    
    # 创建图表
    fig, axes = plt.subplots(2, 1, figsize=(14, 10))
    
    # 图1: 涨停次数分布直方图（仅统计有涨停的股票）
    ax1 = axes[0]
    limit_counts_sorted = sorted(counter_with_limit.keys())
    counts = [counter_with_limit[k] for k in limit_counts_sorted]
    
    bars = ax1.bar(limit_counts_sorted, counts, color='steelblue', alpha=0.7, edgecolor='black')
    ax1.set_xlabel('涨停次数', fontsize=12)
    ax1.set_ylabel('股票数量', fontsize=12)
    ax1.set_title(f'主板股票涨停次数分布图（{start_time} 至 {end_time}）\n仅统计有涨停的股票', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3, axis='y')
    
    # 在柱状图上显示数值
    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}',
                ha='center', va='bottom', fontsize=9)
    
    # 添加统计信息文本框
    stats_text = f'总股票数: {total_stocks}\n有涨停股票数: {stocks_with_limit_count}\n无涨停股票数: {stocks_without_limit}'
    ax1.text(0.98, 0.98, stats_text, transform=ax1.transAxes,
            fontsize=10, verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    # 图2: 涨停次数分布饼图（仅统计有涨停的股票）
    ax2 = axes[1]
    # 将涨停次数分组，便于展示
    # 1次、2次、3次、4次、5次、6-10次、11-20次、20次以上
    groups = {
        '1次': 0,
        '2次': 0,
        '3次': 0,
        '4次': 0,
        '5次': 0,
        '6-10次': 0,
        '11-20次': 0,
        '20次以上': 0
    }
    
    for count in limit_counts_only:
        if count == 1:
            groups['1次'] += 1
        elif count == 2:
            groups['2次'] += 1
        elif count == 3:
            groups['3次'] += 1
        elif count == 4:
            groups['4次'] += 1
        elif count == 5:
            groups['5次'] += 1
        elif 6 <= count <= 10:
            groups['6-10次'] += 1
        elif 11 <= count <= 20:
            groups['11-20次'] += 1
        else:
            groups['20次以上'] += 1
    
    # 过滤掉为0的组
    groups_filtered = {k: v for k, v in groups.items() if v > 0}
    
    if groups_filtered:
        colors = plt.cm.Set3(range(len(groups_filtered)))
        wedges, texts, autotexts = ax2.pie(
            groups_filtered.values(),
            labels=groups_filtered.keys(),
            autopct='%1.1f%%',
            startangle=90,
            colors=colors,
            textprops={'fontsize': 10}
        )
        ax2.set_title(f'涨停次数分组分布（仅统计有涨停的股票）', fontsize=14, fontweight='bold')
        
        # 美化百分比文字
        for autotext in autotexts:
            autotext.set_color('black')
            autotext.set_fontweight('bold')
    
    plt.tight_layout()
    
    # 保存图表和结果文件到results目录
    # 脚本所在目录的results子目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(script_dir, 'results')
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    
    chart_path = os.path.join(results_dir, f'limit_up_distribution_{start_time}_{end_time}.png')
    plt.savefig(chart_path, dpi=300, bbox_inches='tight')
    info(f"图表已保存至: {chart_path}")
    
    # 保存详细数据到CSV
    df_detail = pd.DataFrame(stocks_with_limit)
    df_detail = df_detail.sort_values('limit_count', ascending=False)
    csv_path = os.path.join(results_dir, f'limit_up_detail_{start_time}_{end_time}.csv')
    df_detail.to_csv(csv_path, index=False, encoding='utf-8-sig')
    info(f"详细数据已保存至: {csv_path}")
    
    # 生成统计摘要
    summary_path = os.path.join(results_dir, f'limit_up_summary_{start_time}_{end_time}.txt')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("主板股票涨停次数分布分析报告\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"数据范围: {start_time} 至 {end_time}\n")
        f.write(f"总股票数: {total_stocks}\n")
        f.write(f"有涨停的股票数: {stocks_with_limit_count}\n")
        f.write(f"无涨停的股票数: {stocks_without_limit}\n")
        f.write(f"有涨停股票占比: {stocks_with_limit_count/total_stocks*100:.2f}%\n\n")
        
        f.write("-" * 80 + "\n")
        f.write("涨停次数分布统计（仅统计有涨停的股票）\n")
        f.write("-" * 80 + "\n")
        f.write(f"{'涨停次数':<10} {'股票数量':<10} {'占比':<12} {'累计占比':<12}\n")
        f.write("-" * 80 + "\n")
        
        cumulative_percentage = 0.0
        for count in sorted(counter_with_limit.keys()):
            stock_num = counter_with_limit[count]
            percentage = stock_num / stocks_with_limit_count * 100
            cumulative_percentage += percentage
            f.write(f"{count:<10} {stock_num:<10} {percentage:>10.2f}% {cumulative_percentage:>10.2f}%\n")
        
        f.write("\n" + "-" * 60 + "\n")
        f.write("分组统计\n")
        f.write("-" * 60 + "\n")
        for group_name, group_count in groups_filtered.items():
            percentage = group_count / stocks_with_limit_count * 100
            f.write(f"{group_name}: {group_count} 只 ({percentage:.2f}%)\n")
        
        f.write("\n" + "-" * 60 + "\n")
        f.write("关键统计指标\n")
        f.write("-" * 60 + "\n")
        if limit_counts_only:
            f.write(f"平均涨停次数: {pd.Series(limit_counts_only).mean():.2f}\n")
            f.write(f"中位数涨停次数: {pd.Series(limit_counts_only).median():.2f}\n")
            f.write(f"最大涨停次数: {max(limit_counts_only)}\n")
            f.write(f"最小涨停次数: {min(limit_counts_only)}\n")
            f.write(f"涨停次数标准差: {pd.Series(limit_counts_only).std():.2f}\n")
    
    info(f"统计摘要已保存至: {summary_path}")
    
    # 打印关键统计信息
    info("\n" + "=" * 60)
    info("关键统计信息")
    info("=" * 60)
    if limit_counts_only:
        info(f"平均涨停次数: {pd.Series(limit_counts_only).mean():.2f}")
        info(f"中位数涨停次数: {pd.Series(limit_counts_only).median():.2f}")
        info(f"最大涨停次数: {max(limit_counts_only)}")
        info(f"最小涨停次数: {min(limit_counts_only)}")
    
    info("\n报告生成完成！")


if __name__ == "__main__":
    generate_report()
