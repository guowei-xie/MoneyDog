"""
MoneyDog 主程序入口
量化交易系统主程序
"""
import configparser
import importlib
from utils.logger import info, error


def load_strategy():
    """
    根据配置文件动态加载策略类
    Returns:
        策略实例
    """
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    
    # 读取策略配置
    strategy_module_name = config.get('STRATEGY', 'strategy_module')
    strategy_class_name = config.get('STRATEGY', 'strategy_class')
    
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