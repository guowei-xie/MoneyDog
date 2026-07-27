import os
import gc

import duckdb

from utils.backtest_config import get_data_path


class DuckDBHelper:
    def __init__(self) -> None:
        """
        初始化 DuckDB 连接。DB 路径统一经 backtest_config 读取（__file__ 定位项目根），
        不依赖当前工作目录。
        """
        self.db_path = get_data_path()

        # 检查父目录是否存在，不存在则创建
        parent_dir = os.path.dirname(os.path.abspath(self.db_path))
        if not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        self.conn = duckdb.connect(self.db_path)

    def close(self) -> None:
        """关闭数据库连接。"""
        if self.conn:
            self.conn.close()
            # 强制垃圾回收释放连接相关资源
            gc.collect()
