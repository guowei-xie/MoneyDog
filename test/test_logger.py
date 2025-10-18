"""
日志工具测试模块
测试日志工具的各种功能和使用场景
"""

import os
import sys
import time
import traceback
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger, info, debug, warning, error, exception, critical


def test_basic_logging():
    """
    测试基本日志功能
    测试不同级别的日志输出
    """
    print("=" * 50)
    print("测试基本日志功能")
    print("=" * 50)
    
    # 使用便捷函数
    info("这是一条信息日志")
    debug("这是一条调试日志")
    warning("这是一条警告日志")
    error("这是一条错误日志")
    critical("这是一条严重错误日志")
    
    print("基本日志测试完成\n")


def test_logger_instance():
    """
    测试日志器实例功能
    测试使用不同名称的日志器
    """
    print("=" * 50)
    print("测试日志器实例功能")
    print("=" * 50)
    
    # 创建不同模块的日志器
    data_logger = get_logger("DataProcessor")
    trade_logger = get_logger("TradeEngine")
    risk_logger = get_logger("RiskManager")
    
    # 模拟数据处理
    data_logger.info("开始处理市场数据")
    data_logger.debug("加载股票列表...")
    data_logger.info("数据加载完成，共处理 1000 只股票")
    
    # 模拟交易引擎
    trade_logger.info("交易引擎启动")
    trade_logger.debug("初始化交易接口...")
    trade_logger.warning("检测到网络延迟较高")
    
    # 模拟风险管理
    risk_logger.info("风险管理系统启动")
    risk_logger.warning("检测到异常波动，启动风险控制")
    risk_logger.error("风险指标超出阈值")
    
    print("日志器实例测试完成\n")


def test_exception_handling():
    """
    测试异常处理功能
    测试异常日志记录和堆栈跟踪
    """
    print("=" * 50)
    print("测试异常处理功能")
    print("=" * 50)
    
    # 测试普通异常
    try:
        result = 10 / 0
    except ZeroDivisionError as e:
        error(f"除零错误: {e}")
        exception("除零异常详细信息:")
    
    # 测试复杂异常
    try:
        # 模拟复杂的业务逻辑
        data = {"prices": [100, 200, 300]}
        average_price = sum(data["prices"]) / len(data["prices"])
        
        # 故意引发异常
        risky_operation()
        
    except Exception as e:
        error(f"业务逻辑执行失败: {e}")
        exception("业务异常详细信息:")
    
    print("异常处理测试完成\n")


def risky_operation():
    """
    模拟可能出错的操作
    """
    # 模拟一些可能出错的操作
    data = None
    return data["key"]  # 这里会引发KeyError


def test_performance_logging():
    """
    测试性能日志功能
    测试大量日志输出的性能
    """
    print("=" * 50)
    print("测试性能日志功能")
    print("=" * 50)
    
    start_time = time.time()
    
    # 生成大量日志
    for i in range(100):
        info(f"处理第 {i+1} 条记录")
        if i % 10 == 0:
            debug(f"进度: {i+1}/100")
    
    end_time = time.time()
    duration = end_time - start_time
    
    info(f"性能测试完成，耗时: {duration:.3f} 秒")
    print(f"性能测试完成，耗时: {duration:.3f} 秒\n")


def test_log_file_creation():
    """
    测试日志文件创建功能
    检查日志文件是否正确创建
    """
    print("=" * 50)
    print("测试日志文件创建功能")
    print("=" * 50)
    
    # 记录一些测试日志
    info("测试日志文件创建")
    debug("检查日志文件是否存在")
    
    # 检查日志文件
    logs_dir = "logs"
    if os.path.exists(logs_dir):
        log_files = [f for f in os.listdir(logs_dir) if f.endswith('.log')]
        info(f"找到 {len(log_files)} 个日志文件")
        
        for log_file in log_files:
            file_path = os.path.join(logs_dir, log_file)
            file_size = os.path.getsize(file_path)
            info(f"日志文件: {log_file}, 大小: {file_size} 字节")
    else:
        warning("日志目录不存在")
    
    print("日志文件测试完成\n")


def test_log_formatting():
    """
    测试日志格式化功能
    测试不同格式的日志消息
    """
    print("=" * 50)
    print("测试日志格式化功能")
    print("=" * 50)
    
    # 测试字符串格式化
    user_id = "user123"
    balance = 10000.50
    info(f"用户 {user_id} 当前余额: {balance:.2f}")
    
    # 测试复杂对象
    portfolio = {
        "stocks": ["AAPL", "GOOGL", "MSFT"],
        "total_value": 50000,
        "profit": 2500.75
    }
    info(f"投资组合信息: {portfolio}")
    
    # 测试多行消息
    multi_line_msg = """
    系统状态报告:
    - CPU使用率: 45%
    - 内存使用率: 60%
    - 磁盘使用率: 30%
    - 网络状态: 正常
    """
    info(f"系统状态{multi_line_msg}")
    
    print("日志格式化测试完成\n")


def test_different_log_levels():
    """
    测试不同日志级别的过滤
    演示不同级别日志的显示效果
    """
    print("=" * 50)
    print("测试不同日志级别")
    print("=" * 50)
    
    # 创建测试日志器
    test_logger = get_logger("LevelTest")
    
    # 输出所有级别的日志
    test_logger.debug("这是DEBUG级别日志 - 通常用于详细调试信息")
    test_logger.info("这是INFO级别日志 - 一般信息记录")
    test_logger.warning("这是WARNING级别日志 - 警告信息")
    test_logger.error("这是ERROR级别日志 - 错误信息")
    test_logger.critical("这是CRITICAL级别日志 - 严重错误")
    
    print("日志级别测试完成\n")


def main():
    """
    主测试函数
    运行所有日志功能测试
    """
    print("开始日志工具功能测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        # 运行各项测试
        test_basic_logging()
        test_logger_instance()
        test_exception_handling()
        test_performance_logging()
        test_log_file_creation()
        test_log_formatting()
        test_different_log_levels()
        
        # 测试完成
        info("=" * 50)
        info("所有日志功能测试完成！")
        info("=" * 50)
        
        print("=" * 50)
        print("所有日志功能测试完成！")
        print("=" * 50)
        print("请检查 logs/ 目录下的日志文件查看详细输出")
        
    except Exception as e:
        error(f"测试过程中发生错误: {e}")
        exception("测试异常详细信息:")
        return 1
    
    return 0


if __name__ == "__main__":
    """
    测试程序入口
    当直接运行此文件时执行所有测试
    """
    exit_code = main()
    exit(exit_code)
