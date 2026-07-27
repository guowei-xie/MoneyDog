"""
MoneyDog 主程序入口
量化交易系统主程序
"""
import importlib
from utils.logger import info, error
from utils.backtest_config import get_strategy_target


def load_strategy():
    """
    根据配置文件动态加载策略类
    Returns:
        策略实例
    """
    # 策略模块名/类名统一经 backtest_config 读取（__file__ 定位项目根，不依赖 CWD）
    strategy_module_name, strategy_class_name = get_strategy_target()
    
    try:
        # 动态导入策略模块
        module_path = f'strategys.{strategy_module_name}'
        strategy_module = importlib.import_module(module_path)
        
        # 获取策略类
        strategy_class = getattr(strategy_module, strategy_class_name)
        
        info(f"成功加载策略: {strategy_module_name}.{strategy_class_name}")
        return strategy_class()
    except ImportError as e:
        error(f"导入策略模块失败: {module_path}, 错误: {e}")
        raise
    except AttributeError as e:
        error(f"策略类不存在: {strategy_class_name}, 错误: {e}")
        raise
    except Exception as e:
        error(f"加载策略失败: {e}")
        raise


# 主程序入口
if __name__ == "__main__":
    info("MoneyDog 主程序运行开始")
    try:
        strategy = load_strategy()
        strategy.run()
    except Exception as e:
        error(f"程序运行失败: {e}")
        raise