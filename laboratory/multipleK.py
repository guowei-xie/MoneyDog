"""
多K线工具库
"""
import pandas as pd
from laboratory.singleK import is_limit
from utils.logger import info, error, debug

def get_limit_board_number(stock_code: str, daily_bars: pd.DataFrame) -> int:
    """
    获取涨停是第几板（从后向前数，连续涨停K线的数量，遇到非涨停即终止，建议最后一条数据为涨停日K线）
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框（建议最后一条数据为涨停日）
    Returns:
        int: 涨停是第几板
    """
    debug(f"获取涨停是第几板: {stock_code}")
    
    # 如果数据为空，直接返回0
    if len(daily_bars) == 0:
        return 0

    limit_board = 0
    for idx in range(len(daily_bars) - 1, -1, -1):
        close = daily_bars['close'].iloc[idx]
        preClose = daily_bars['preClose'].iloc[idx]
        if is_limit(stock_code, close, preClose):
            limit_board += 1
        else:
            break

    return limit_board

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

    # 首板要求至少2条K线数据
    if len(daily_bars) < 2:
        debug(f"日K线数据不足2条: {stock_code}, 数据: {daily_bars}")
        return False

    return get_limit_board_number(stock_code, daily_bars) == 1

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

# 获取最近N天内的最后一次涨停日K线数据
def get_last_limit_day_kline(stock_code: str, daily_bars: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """
    获取最近N天内的最后一次涨停日的单日K线数据（仅涨停日那一天的K线数据）
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
        n: 最近N天内的最后一次涨停日
    Returns:
        pd.DataFrame: 最近的涨停日K线数据，不存在时返回pd.DataFrame()
    """
    last_limit_day = get_last_limit_day(stock_code, daily_bars, n)
    if last_limit_day == -1:
        return pd.DataFrame()
    return daily_bars.loc[last_limit_day:last_limit_day]

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

def get_ma_list(daily_bars: pd.DataFrame, period: int = 5, count: int = -1) -> list:
    """
    计算MA均线列表
    Args:
        daily_bars: 日K线数据框
        period: 均线周期，默认为5
        count: 返回最后几个交易日的MA均线列表，默认为-1，返回所有交易日的MA均线列表
    Returns:
        ma_list: MA均线列表
    """
    if count != -1:
        ma_list = daily_bars['close'].rolling(window=period).mean().iloc[-count:].tolist()
    else:
        ma_list = daily_bars['close'].rolling(window=period).mean().tolist()
    ma_list = [round(ma, 2) for ma in ma_list]
    return ma_list

def get_average_volume(daily_bars: pd.DataFrame, period: int = 5) -> float:
    """
    滑动计算日均成交量
    Args:
        daily_bars: 日K线数据框
        period: 滑动周期，默认为5
    Returns:
        daily_bars: 新增'average_volume'列，包含每个交易日日均成交量
    """
    daily_bars = daily_bars.copy()
    daily_bars['average_volume'] = daily_bars['volume'].rolling(window=period).mean()
    return daily_bars

# 计算滑动窗口最大成交量
def get_max_volume(daily_bars: pd.DataFrame, period: int = 5) -> float:
    """
    计算滑动窗口最大成交量
    Args:
        daily_bars: 日K线数据框
        period: 滑动周期，默认为5
    Returns:
        daily_bars: 新增'max_volume'列，包含每个交易日滑动窗口最大成交量
    """
    daily_bars = daily_bars.copy()
    daily_bars['max_volume'] = daily_bars['volume'].rolling(window=period).max()
    return daily_bars

def get_volume_change_rate(daily_bars: pd.DataFrame) -> pd.DataFrame:
    """
    计算每个交易日成交量相对前一个交易日成交量变化率
    Args:
        daily_bars: 日K线数据框
    Returns:
        daily_bars: 新增'volume_change_rate'列，包含每个交易日成交量相对前一个交易日的变化率（第一个交易日为NaN）
    """
    if len(daily_bars) < 2:
        daily_bars = daily_bars.copy()
        daily_bars['volume_change_rate'] = float('nan')
        return daily_bars
    daily_bars = daily_bars.copy()
    daily_bars['volume_change_rate'] = daily_bars['volume'].pct_change()
    return daily_bars
    

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

# 均线空头排列
def is_ma_bearish(daily_bars: pd.DataFrame) -> bool:
    """
    均线空头排列（MA5<MA10<MA20<MA30）
    Args:
        daily_bars: 日K线数据框
    Returns:
        bool: 是否空头排列，True表示空头排列，False表示不空头排列
    """
    ma5 = get_ma(daily_bars=daily_bars, period=5)
    ma10 = get_ma(daily_bars=daily_bars, period=10)
    ma20 = get_ma(daily_bars=daily_bars, period=20)
    ma30 = get_ma(daily_bars=daily_bars, period=30)
    if ma5 < ma10 < ma20 < ma30:
        return True
    return False

# MACD计算
def get_macd(daily_bars: pd.DataFrame, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> pd.DataFrame:
    """
    计算MACD指标（DIF、DEA、MACD柱）
    
    Args:
        daily_bars (pd.DataFrame): 包含每日行情数据的DataFrame，必须包含'close'列
        fast_period (int): 快线周期，默认12
        slow_period (int): 慢线周期，默认26
        signal_period (int): 信号线周期，默认9
        
    Returns:
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
    df['macd'] = 2 * (df['dif'] - df['dea'])
    
    # 删除临时计算的EMA列（可选）
    df.drop(['ema_fast', 'ema_slow'], axis=1, inplace=True)
    
    return df

def is_macd_top(macd_data: pd.DataFrame) -> bool:
    """
    判断MACD柱是否见顶
    
    Args:
        macd_data: 包含MACD列的行情数据
        
    Returns:
        bool: MACD柱见顶返回True，否则返回False
    """
    # 检查数据量是否足够
    if len(macd_data) < 4:
        return False
    
    # 获取最近四根MACD柱值
    m1, m2, m3, m4 = macd_data['macd'].iloc[-1:-5:-1]
    
    # 判断是否满足见顶条件：m1 < m2 < m3 > m4
    return m1 < m2 < m3 > m4 and m1 > 0 and m2 > 0 and m3 > 0 and m4 > 0

def is_macd_bottom(macd_data: pd.DataFrame) -> bool:
    """
    判断MACD柱是否见底（绿柱缩短后企稳的 V 形拐点）。

    记最近五根 MACD 柱由新到旧为 m1..m5（m1=最新）。见底条件（与实现一致）：
    m1 > m2 > m3 > m4 < m5，且五根均为负（绿柱）。
    即绿柱经历 m5→m4 的走长到 m4 的最长，再 m4→m1 逐根缩短的拐头企稳形态。

    Args:
        macd_data: 包含MACD列的行情数据
    Returns:
        bool: MACD柱见底返回True，否则返回False
    """
    if len(macd_data) < 5:
        return False

    # 获取最近五根MACD柱值
    m1, m2, m3, m4, m5 = macd_data['macd'].iloc[-1:-6:-1]

    # 判断是否满足见底条件：m1 > m2 > m3 > m4 < m5，且全为负
    return m1 > m2 > m3 > m4 < m5 and m1 < 0 and m2 < 0 and m3 < 0 and m4 < 0 and m5 < 0

# 计算BOLL带（中轨、上轨、下轨）
def get_boll(daily_bars: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    计算布林带（中轨、上轨、下轨）
    Args:
        daily_bars: 日K线数据框
        period: 均线周期，默认为20
    Returns:
        boll_df: 含原数据及boll中轨、上轨、下轨的数据框
    """
    boll_df = daily_bars.copy()
    # 计算中轨（移动平均线）
    boll_df['boll_mid'] = boll_df['close'].rolling(window=period, min_periods=period).mean()
    # 计算标准差
    rolling_std = boll_df['close'].rolling(window=period, min_periods=period).std()
    # 计算上轨（中轨 + 2倍标准差）
    boll_df['boll_upper'] = boll_df['boll_mid'] + 2 * rolling_std
    # 计算下轨（中轨 - 2倍标准差）
    boll_df['boll_lower'] = boll_df['boll_mid'] - 2 * rolling_std
    return boll_df

# 利用分时快照，构造动态日线级别K线
def get_dynamic_daily_kline(bars: pd.DataFrame) -> pd.DataFrame:
    """
    利用分时快照，构造动态日线级别K线
    包含："open, high, low, close, volume, amount"
    Args:
        bars: 分时快照
    Returns:
        pd.DataFrame: 动态日线级别K线
    """
    # 检查 bars 是否为空
    if bars is None or bars.empty:
        return pd.DataFrame()

    # 构建一行字典
    kline_dict = {
        'open': bars['open'].iloc[0],
        'high': bars['high'].max(),
        'low': bars['low'].min(),
        'close': bars['close'].iloc[-1],
        'volume': bars['volume'].sum(),
        'amount': bars['amount'].sum()
    }

    # 返回单行DataFrame，列保持一致
    return pd.DataFrame([kline_dict])

# MA5底部图形
def get_ma5_bottom(daily_bars: pd.DataFrame, left_count: int = 5, right_count: int = 1) -> pd.DataFrame:
    """
    MA5底部图形判断
    对于每个交易日T，如果T-left_count到T-1日连续MA5下跌，且T+1到T+right_count日连续MA5上涨，则T日是MA5底部
    
    Args:
        daily_bars: 日K线数据框
        left_count: 左侧确认长度天数（默认5）
        right_count: 右侧确认长度天数（默认1）
    Returns:
        pd.DataFrame: 包含原始数据和新增'is_ma5_bottom'列的数据框，'is_ma5_bottom'列标记是否为MA5底部
    """
    # 复制数据框，避免修改原始数据
    df = daily_bars.copy()
    
    # 如果数据为空，直接返回
    if len(df) == 0:
        df['is_ma5_bottom'] = False
        return df
    
    # 计算MA5值
    df['ma5'] = df['close'].rolling(window=5, min_periods=5).mean()
    
    # 计算MA5的变化量（diff = MA5[t] - MA5[t-1]）
    ma5_diff = df['ma5'].diff()
    
    # 检查左侧left_count天是否连续下跌（diff < 0）：窗口内全为 True 等价于布尔和==窗口长度
    # 对于T日，检查T-left_count到T-1这left_count天的diff是否都小于0
    left_decreasing = (
        (ma5_diff < 0).rolling(window=left_count, min_periods=left_count).sum() == left_count
    ).shift(1)  # 对齐到T日
    left_decreasing = left_decreasing.fillna(0).astype(bool)

    # 检查右侧right_count天是否连续上涨（diff > 0）
    # 对于T日，检查T+1到T+right_count这right_count天的diff是否都大于0
    right_increasing = (
        (ma5_diff > 0).rolling(window=right_count, min_periods=right_count).sum() == right_count
    ).shift(-right_count)  # 对齐到T日
    right_increasing = right_increasing.fillna(0).astype(bool)
    
    # 合并条件：左侧连续下跌且右侧连续上涨
    df['is_ma5_bottom'] = (left_decreasing & right_increasing).astype(bool)
    
    # 删除临时计算的ma5列
    # df.drop(['ma5'], axis=1, inplace=True)
    
    return df

# MA5顶部图形
def get_ma5_top(daily_bars: pd.DataFrame, left_count: int = 5, right_count: int = 1) -> pd.DataFrame:
    """
    MA5顶部图形判断
    对于每个交易日T，如果T-left_count到T-1日连续MA5上涨，且T+1到T+right_count日连续MA5下跌，则T日是MA5顶部
    
    Args:
        daily_bars: 日K线数据框
        left_count: 左侧确认长度天数（默认5）
        right_count: 右侧确认长度天数（默认1）
    Returns:
        pd.DataFrame: 包含原始数据和新增'is_ma5_top'列的数据框，'is_ma5_top'列标记是否为MA5顶部
    """
    # 复制数据框，避免修改原始数据
    df = daily_bars.copy()
    
    # 如果数据为空，直接返回
    if len(df) == 0:
        df['is_ma5_top'] = False
        return df
    
    # 计算MA5值
    df['ma5'] = df['close'].rolling(window=5, min_periods=5).mean()
    
    # 计算MA5的变化量（diff = MA5[t] - MA5[t-1]）
    ma5_diff = df['ma5'].diff()
    
    # 检查左侧left_count天是否连续上涨（diff > 0）：窗口内全为 True 等价于布尔和==窗口长度
    # 对于T日，检查T-left_count到T-1这left_count天的diff是否都大于0
    left_increasing = (
        (ma5_diff > 0).rolling(window=left_count, min_periods=left_count).sum() == left_count
    ).shift(1)  # 对齐到T日
    left_increasing = left_increasing.fillna(0).astype(bool)

    # 检查右侧right_count天是否连续下跌（diff < 0）
    # 对于T日，检查T+1到T+right_count这right_count天的diff是否都小于0
    right_decreasing = (
        (ma5_diff < 0).rolling(window=right_count, min_periods=right_count).sum() == right_count
    ).shift(-right_count)  # 对齐到T日
    right_decreasing = right_decreasing.fillna(0).astype(bool)
    
    # 合并条件：左侧连续上涨且右侧连续下跌
    df['is_ma5_top'] = (left_increasing & right_decreasing).astype(bool)
    
    # 删除临时计算的ma5列
    # df.drop(['ma5'], axis=1, inplace=True)
    
    return df