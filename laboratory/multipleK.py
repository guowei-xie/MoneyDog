"""
多K线工具库
"""
import pandas as pd
from laboratory.singleK import is_limit
from utils.logger import info, error, debug


def is_first_board(stock_code: str, daily_bars: pd.DataFrame) -> bool:
    """
    判断是否符合首板图形要求
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
    Returns:
        bool: 是否符合图形要求，True表示符合，False表示不符合
    """
    debug(f"判断是否符合首板图形要求: {stock_code}")

    # 至少需要2条数据
    if len(daily_bars) < 2:
        debug(f"日K线数据不足2条: {stock_code}, 数据: {daily_bars}")
        return False
    
    # 判断当日是否涨停
    if not is_limit(stock_code, daily_bars['close'].iloc[-1], daily_bars['preClose'].iloc[-1]):
        return False
    
    # 判断前一日是否涨停
    if is_limit(stock_code, daily_bars['close'].iloc[-2], daily_bars['preClose'].iloc[-2]):
        return False
    
    return True

def get_last_limit_day(stock_code: str, daily_bars: pd.DataFrame, n: int = 5) -> int:
    """
    获取最近N天内的最后一次涨停日
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
        n: 最近N天内的最后一次涨停日
    Returns:
        int: 最近的涨停日索引, -1表示不存在
    """
    debug(f"获取最近{n}天内的最后一次涨停日: {stock_code}")

    daily_bars_last = daily_bars.iloc[-n:].copy()
    # debug(f"截断数据: {daily_bars_last}")

    # 从后往前遍历，找到最近的涨停日
    for index, row in daily_bars_last.iloc[::-1].iterrows():
        if is_limit(stock_code, row['close'], row['preClose']):
            # debug(f"获取成功, 索引: {index}")
            return index
    return -1

def get_daily_bars_by_date(daily_bars: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    """
    获取指定日期的K线数据
    Args:
        daily_bars: 日K线数据框
        start_date: 开始日期，格式为'YYYYMMDD'
        end_date: 结束日期，格式为'YYYYMMDD'
    Returns:
        pd.DataFrame: 指定日期的K线数据，不存在时返回pd.DataFrame()
    """
    daily_bars_last = daily_bars.loc[start_date:end_date]
    return daily_bars_last

# 判断成交量逐日递减
def is_volume_decreasing(daily_bars: pd.DataFrame, decreasing_ratio: float = 0.0) -> bool:
    """
    判断成交量逐日递减
    Args:
        daily_bars: 日K线数据框
        decreasing_ratio: 递减比例，默认为0
    Returns:
        bool: 是否逐日递减，True表示逐日递减，False表示不逐日递减
    """
    if len(daily_bars) < 2:
        return False
    for i in range(1, len(daily_bars)):
        prev_volume = daily_bars['volume'].iloc[i-1]
        curr_volume = daily_bars['volume'].iloc[i]
        if curr_volume > prev_volume * (1 - decreasing_ratio):
            return False
    return True

# 计算MA均线
def get_ma(daily_bars: pd.DataFrame, period: int = 5) -> float:
    """
    计算MA均线
    Args:
        daily_bars: 日K线数据框
        period: 均线周期，默认为5
    Returns:
        ma_price: MA均线价格
    """
    ma_price = daily_bars['close'].rolling(window=period).mean().iloc[-1]
    return round(ma_price, 2)

# 均线多头排列（MA5>MA10>MA20>MA30）
def is_ma_bullish(daily_bars: pd.DataFrame) -> bool:
    """
    均线多头排列（MA5>MA10>MA20>MA30）
    Args:
        daily_bars: 日K线数据框
    Returns:
        bool: 是否多头排列，True表示多头排列，False表示不多头排列
    """
    ma5 = get_ma(daily_bars=daily_bars, period=5)
    ma10 = get_ma(daily_bars=daily_bars, period=10)
    ma20 = get_ma(daily_bars=daily_bars, period=20)
    ma30 = get_ma(daily_bars=daily_bars, period=30)
    if ma5 > ma10 > ma20 > ma30:
        return True
    return False

# MACD计算
def get_macd(daily_bars: pd.DataFrame, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> pd.DataFrame:
    """
    计算MACD指标（DIF、DEA、MACD柱）
    
    参数:
        daily_bars (pd.DataFrame): 包含每日行情数据的DataFrame，必须包含'close'列
        fast_period (int): 快线周期，默认12
        slow_period (int): 慢线周期，默认26
        signal_period (int): 信号线周期，默认9
        
    返回:
        pd.DataFrame: 包含原始数据和新增的MACD相关列的DataFrame
    """
    # 复制原始数据，避免修改原始DataFrame
    df = daily_bars.copy()
    
    # 计算快线（12日EMA）和慢线（26日EMA）
    df['ema_fast'] = df['close'].ewm(span=fast_period, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_period, adjust=False).mean()
    
    # 计算DIF（离差值）
    df['dif'] = df['ema_fast'] - df['ema_slow']
    
    # 计算DEA（信号线，即DIF的9日EMA）
    df['dea'] = df['dif'].ewm(span=signal_period, adjust=False).mean()
    
    # 计算MACD柱（Histogram）
    df['macd'] = df['dif'] - df['dea']
    
    # 删除临时计算的EMA列（可选）
    df.drop(['ema_fast', 'ema_slow'], axis=1, inplace=True)
    
    return df