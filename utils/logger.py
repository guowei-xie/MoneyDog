"""
日志工具模块
提供统一的日志记录功能，支持文件输出、控制台输出和配置化管理
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional
import configparser


class Logger:
    """
    日志工具类
    提供统一的日志记录功能，支持多种输出方式和配置化管理
    """
    
    def __init__(self, name: str = "MoneyDog", config_file: str = "config.ini"):
        """
        初始化日志器
        
        Args:
            name: 日志器名称
            config_file: 配置文件路径
        """
        self.name = name
        self.config_file = config_file
        self.logger = None
        self._setup_logger()
    
    def _setup_logger(self):
        """
        设置日志器配置
        从配置文件读取日志级别，设置文件和控制台输出
        """
        # 创建日志器
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(logging.DEBUG)
        
        # 避免重复添加处理器
        if self.logger.handlers:
            return
        
        # 读取配置
        log_level = self._get_log_level()
        
        # 创建日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # 文件处理器
        self._setup_file_handler(formatter, log_level)
    
    def _get_log_level(self) -> int:
        """
        从配置文件读取日志级别
        
        Returns:
            日志级别
        """
        try:
            config = configparser.ConfigParser()
            if os.path.exists(self.config_file):
                config.read(self.config_file, encoding='utf-8')
                level_str = config.get('LOGGING', 'level', fallback='INFO').upper()
                return getattr(logging, level_str, logging.INFO)
        except Exception as e:
            print(f"读取日志配置失败: {e}")
        
        return logging.INFO
    
    def _setup_file_handler(self, formatter: logging.Formatter, log_level: int):
        """
        设置文件处理器
        
        Args:
            formatter: 日志格式器
            log_level: 日志级别
        """
        try:
            # 确保logs目录存在
            logs_dir = "logs"
            if not os.path.exists(logs_dir):
                os.makedirs(logs_dir)
            
            # 按日期创建日志文件
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = os.path.join(logs_dir, f"{self.name}_{today}.log")
            
            # 文件处理器
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            
        except Exception as e:
            print(f"设置文件日志处理器失败: {e}")
    
    def debug(self, message: str, *args, **kwargs):
        """
        记录调试信息
        
        Args:
            message: 日志消息
            *args: 格式化参数
            **kwargs: 额外参数
        """
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """
        记录一般信息
        
        Args:
            message: 日志消息
            *args: 格式化参数
            **kwargs: 额外参数
        """
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """
        记录警告信息
        
        Args:
            message: 日志消息
            *args: 格式化参数
            **kwargs: 额外参数
        """
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """
        记录错误信息
        
        Args:
            message: 日志消息
            *args: 格式化参数
            **kwargs: 额外参数
        """
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """
        记录严重错误信息
        
        Args:
            message: 日志消息
            *args: 格式化参数
            **kwargs: 额外参数
        """
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs):
        """
        记录异常信息（包含异常堆栈）
        
        Args:
            message: 日志消息
            *args: 格式化参数
            **kwargs: 额外参数
        """
        self.logger.exception(message, *args, **kwargs)


# 创建全局日志器实例
logger = Logger()


def get_logger(name: Optional[str] = None) -> Logger:
    """
    获取日志器实例
    
    Args:
        name: 日志器名称，如果为None则返回默认日志器
        
    Returns:
        日志器实例
    """
    if name is None:
        return logger
    return Logger(name)


# 便捷函数
def debug(message: str, *args, **kwargs):
    """调试日志"""
    logger.debug(message, *args, **kwargs)


def info(message: str, *args, **kwargs):
    """信息日志"""
    logger.info(message, *args, **kwargs)


def warning(message: str, *args, **kwargs):
    """警告日志"""
    logger.warning(message, *args, **kwargs)


def error(message: str, *args, **kwargs):
    """错误日志"""
    logger.error(message, *args, **kwargs)


def critical(message: str, *args, **kwargs):
    """严重错误日志"""
    logger.critical(message, *args, **kwargs)


def exception(message: str, *args, **kwargs):
    """异常日志"""
    logger.exception(message, *args, **kwargs)
