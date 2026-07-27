import os
import duckdb
import gc
import configparser

class DuckDBHelper:
    def __init__(self):
        """
        初始化DuckDB连接
        """
        config = configparser.ConfigParser()
        with open('config.ini', 'r', encoding='utf-8') as f:
            config.read_file(f)
        self.db_path = config.get('DATA', 'data_path')

        # 检查父目录是否存在，不存在则创建
        parent_dir = os.path.dirname(os.path.abspath(self.db_path))
        if not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        self.conn = duckdb.connect(self.db_path)

    def close(self):
        """
        关闭数据库连接
        """
        if self.conn:
            self.conn.close()
            # 强制垃圾回收释放连接相关资源
            gc.collect()

    def read_duckdb_table(self, table_name, limit=100):
        """
        读取DuckDB中的表, limit为读取的行数，默认读取100行
        """
        return self.conn.execute(f"SELECT * FROM {table_name} LIMIT {limit}").df()

    def get_stock_list_in_sector(self, sector_name):
        """
        获取板块成分股。本库从 stock_list 表返回全部股票代码。
        Args:
            sector_name: 板块名称(如: '沪深A股')，当前未使用，保留接口兼容
        Returns:
            list: 股票代码列表
        """
        sql = "SELECT DISTINCT code FROM stock_list ORDER BY code"
        df = self.conn.execute(sql).df()
        return df["code"].values.tolist()



