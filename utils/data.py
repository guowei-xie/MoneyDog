"""
数据工具模块
提供数据处理和获取功能
适配新库 moneydog.duckdb：表 stock_1day_bars / stock_1m_bars / index_1day_bars，
时间戳为秒级，无 stock_list 表，指数 code 无后缀（如 000001）。
"""
import pandas as pd
from utils.logger import debug, error
from utils.util import get_stock_market_type
from utils.duckdb import DuckDBHelper
from utils.util import date_to_timestamp

duckdb_helper = DuckDBHelper()

# 新库表名映射（对外仍可用旧表名语义，如 index_daily）
_TABLE_MAP = {
    "daily_1day": "stock_1day_bars",
    "daily_1min": "stock_1m_bars",
    "index_daily": "index_1day_bars",
}

# 指数 code 映射：策略常用 000001.SH，新库为 000001
_INDEX_CODE_TO_DB = {
    "000001.SH": "000001",
    # 中证1000（常见代码：000852.SH；库内通常无后缀）
    "000852.SH": "000852",
}


def has_index_1day_data(index_code: str) -> bool:
    """
    检查数据库中是否存在指定指数的日线行情数据（index_1day_bars）。

    Args:
        index_code: 指数代码，支持带后缀（如 '000852.SH'）或库内代码（如 '000852'）

    Returns:
        bool: 存在返回 True，否则 False
    """
    if not index_code:
        return False
    db_code = _INDEX_CODE_TO_DB.get(index_code, index_code)
    try:
        sql = 'SELECT 1 AS ok FROM "index_1day_bars" WHERE code = ? LIMIT 1'
        df = duckdb_helper.conn.execute(sql, [db_code]).df()
        return not df.empty
    except Exception as e:
        error(f"检查指数日线数据失败 index_code={index_code}: {e}")
        return False


def get_trade_calendar(start_time: str, end_time: str, format: str = "number") -> list:
    """
    获取交易日历（从新库 trade_calendar 表读取，避免依赖 akshare）。
    Args:
        start_time: 开始时间，如 '20240101' 或 '2024-01-01'
        end_time: 结束时间
        format: 'number' 返回如 20240101，'str' 返回如 '2024-01-01'
    Returns:
        list: 交易日历
    """
    start = pd.to_datetime(start_time)
    end = pd.to_datetime(end_time)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    try:
        sql = (
            "SELECT trade_date FROM trade_calendar "
            "WHERE trade_date >= ? AND trade_date <= ? ORDER BY trade_date"
        )
        df = duckdb_helper.conn.execute(sql, [start_str, end_str]).df()
    except Exception as e:
        error(f"从 trade_calendar 读取交易日历失败: {e}")
        raise RuntimeError(f"从 trade_calendar 读取交易日历失败: {e}") from e
    dates = pd.to_datetime(df["trade_date"])
    if format == "number":
        return [d.strftime("%Y%m%d") for d in dates]
    if format == "str":
        return [d.strftime("%Y-%m-%d") for d in dates]
    error(f"无效的格式: {format}")
    raise ValueError(f"无效的格式: {format}")


def _is_standard_stock_code(code: str) -> bool:
    """新库可能含 T 开头等非标准 code，只保留 6 位数字+后缀 如 000001.SZ。"""
    if not code or "." not in code or len(code) != 9:
        return False
    prefix, _ = code.split(".", 1)
    return len(prefix) == 6 and prefix.isdigit()


def get_stock_list_in_sector(sector_name: str) -> list:
    """
    获取板块成分股。新库无板块表，返回全市场股票代码（从 stock_1day_bars 去重，仅标准代码）。
    Args:
        sector_name: 板块名称(如: '沪深A股')，当前未使用，保留接口兼容
    Returns:
        list: 股票代码列表
    """
    try:
        sql = "SELECT DISTINCT code FROM stock_1day_bars ORDER BY code"
        df = duckdb_helper.conn.execute(sql).df()
        codes = df["code"].values.tolist()
        return [c for c in codes if _is_standard_stock_code(c)]
    except Exception as e:
        error(f"获取股票列表失败: {e}")
        raise RuntimeError(f"获取股票列表失败: {e}") from e

def get_stock_list_in_main_board() -> list:
    """
    获取沪深A股主板成分股
    Returns:
        list: 沪深A股主板成分股代码列表
    """
    try:
        sector_name = '沪深A股'
        stock_list = get_stock_list_in_sector(sector_name)
        stock_list = [stock for stock in stock_list if get_stock_market_type(stock) == '主板']
        return stock_list
    except Exception as e:
        error(f"获取{sector_name}主板成分股失败: {e}")
        raise RuntimeError(f"获取{sector_name}主板成分股失败: {e}")

# 获取行情数据
def get_daily_bars(
    stock_list: list,
    period: str = "1d",
    start_time: str = "",
    end_time: str = "",
    count: int = -1,
    add_preclose: bool = True,
    table_name: str = "",
) -> dict:
    """
    获取行情数据。新库使用秒级时间戳，表名与 code 已做映射。
    Args:
        stock_list: 股票/指数列表，指数可用 000001.SH（会映射为库内 000001）
        period: 周期 '1d' 或 '1m'
        start_time: 开始时间（如 '20240101'）
        end_time: 结束时间
        count: -1 返回全部；>0 时从最新往前取 count 条
        add_preclose: 是否添加前收盘价
        table_name: 表名语义 'daily_1day' / 'daily_1min' / 'index_daily'，空则按 period 推断
    Returns:
        dict: {stock_code: DataFrame}，key 与传入的 stock_list 一致
    """
    if not stock_list:
        error("股票列表为空")
        raise ValueError("股票列表为空")

    if table_name == "":
        table_name = "daily_1day" if period == "1d" else "daily_1min"
    if period not in ("1d", "1m"):
        error(f"不支持的周期: {period}")
        raise ValueError(f"不支持的周期: {period}")

    raw_table = _TABLE_MAP.get(table_name, table_name)
    is_index = raw_table == "index_1day_bars"

    # 新库为秒级时间戳；与 date_to_timestamp（毫秒）统一为秒
    start_ts = (date_to_timestamp(start_time) // 1000) if start_time else None
    end_ts = (date_to_timestamp(end_time, at_end_of_day=True) // 1000) if end_time else None

    # 指数表 code 无后缀，做请求 code -> 库 code 映射
    if is_index:
        db_codes = [_INDEX_CODE_TO_DB.get(c, c) for c in stock_list]
        code_to_request = {_INDEX_CODE_TO_DB.get(c, c): c for c in stock_list}
    else:
        db_codes = list(stock_list)
        code_to_request = {c: c for c in stock_list}

    code_list_str = ",".join([f"'{c}'" for c in db_codes])
    fields = "code, timestamp, open, high, low, close, volume, amount"
    where_clause = [f"code IN ({code_list_str})"]
    if start_ts is not None:
        where_clause.append(f"timestamp >= {start_ts}")
    if end_ts is not None:
        where_clause.append(f"timestamp <= {end_ts}")
    where_sql = " AND ".join(where_clause)
    sql = f"SELECT {fields} FROM \"{raw_table}\" WHERE {where_sql} ORDER BY code, timestamp"
    df_all = duckdb_helper.conn.execute(sql).df()

    if df_all.empty:
        return {c: pd.DataFrame() for c in stock_list}

    # 统一用 result_code 作为返回 dict 的 key（与请求的 stock_list 一致）
    if is_index:
        df_all["result_code"] = df_all["code"].map(code_to_request)
    else:
        df_all["result_code"] = df_all["code"]

    if add_preclose:
        df_all["preClose"] = df_all.groupby("result_code", sort=False)["close"].shift(1)
    if count > 0:
        df_all = df_all.groupby("result_code", sort=False).tail(count).reset_index(drop=True)

    # 新库时间为秒。分时数据若按 UTC 解析会多 8 小时（数据源将北京时间按 UTC 写入），需先减 8h 再转上海时间；日线只取日期，不受影响。
    _BEIJING_UTC_OFFSET_SEC = 8 * 3600

    if period == "1d":
        df_all["index"] = (
            pd.to_datetime(df_all["timestamp"], unit="s", utc=True)
            .dt.tz_convert("Asia/Shanghai")
            .dt.strftime("%Y%m%d")
        )
    else:
        # 分时：库内时间戳实为“北京时间误当 UTC”写入，减 8 小时后再按 UTC→上海 转换
        ts_corrected = df_all["timestamp"] - _BEIJING_UTC_OFFSET_SEC
        df_all["index"] = (
            pd.to_datetime(ts_corrected, unit="s", utc=True)
            .dt.tz_convert("Asia/Shanghai")
            .dt.strftime("%Y%m%d%H%M%S")
        )
        df_all["timestamp"] = ts_corrected  # 对外 time 列与 index 一致，为校正后秒时间戳

    df_all = df_all.set_index("index")
    # 对外统一列名为 time（与旧接口一致），值为秒级时间戳
    daily_bars = {}
    for code, group_df in df_all.groupby("result_code", sort=False):
        out = group_df.drop(columns=["code", "result_code"])
        if "timestamp" in out.columns:
            out = out.rename(columns={"timestamp": "time"})
        daily_bars[code] = out
    return {c: daily_bars.get(c, pd.DataFrame()) for c in stock_list}


def get_daily_bars_from_cache(
    cache: dict,
    stock_list: list,
    end_time: str,
    count: int,
) -> dict:
    """
    从内存中的日线全量缓存按 end_time、count 切片，返回与 get_daily_bars 相同结构。
    用于多线程选股时避免重复访问 DuckDB。
    Args:
        cache: 全量日线缓存 {stock_code: DataFrame}，DataFrame.index 为 'YYYYMMDD'
        stock_list: 股票列表
        end_time: 截止日期（含），如 '20241130'
        count: 从 end_time 往前取条数，-1 表示全部
    Returns:
        dict: {stock_code: DataFrame}，与 get_daily_bars(..., end_time=end_time, count=count) 一致
    """
    result = {}
    for code in stock_list:
        df = cache.get(code)
        if df is None or df.empty:
            result[code] = pd.DataFrame()
            continue
        # index 为 'YYYYMMDD'，取 index <= end_time 再按 count 截断
        mask = df.index <= end_time
        sliced = df.loc[mask]
        if count > 0:
            sliced = sliced.tail(count)
        result[code] = sliced
    return result
