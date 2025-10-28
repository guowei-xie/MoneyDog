"""
自定义组合图形识别
"""

import pandas as pd
from laboratory.singleK import is_limit, is_one_board
from laboratory.multipleK import get_last_limit_day, get_limit_board_number, get_daily_bars_by_date, is_volume_decreasing, get_ma, is_ma_bullish, get_macd
from utils.logger import info, error, debug

# 判断是否符合日K线图形：涨停后缩量盘整
def is_limit_board_after_volume_consolidation(stock_code: str, daily_bars: pd.DataFrame, n: int = 5, m: int = 10, k: int = 2) -> bool:
    """
    判断是否符合涨停后缩量盘整图形要求
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
        n: 最近{n}个交易日内存在涨停板，且最近一次涨停最多是二板
        m: 最近{m}个交易日内不能存在一字板
        k: 最近{k}个交易日不能是涨停板
    Returns:
        bool: 是否符合图形要求，True表示符合，False表示不符合

    图形要求：
    1. 近{n}个交易日内存在涨停板，且最近一次涨停最多是二板
    2. 近{m}个交易日内不能存在一字板
    3. 最近一次涨停日至少早于当前{k}个交易日
    4. 最近的涨停日次日的成交量不低于涨停日的80%
    5. 最近的涨停日次日至今，成交量逐日递减
    6. 最近的涨停日次日至今，日内震荡幅度处于涨停日价格的-1%~6%之间
    7. 最近的涨停日次日至今，日线收盘价不破涨停日收盘价
    8. 今日收盘价格高于30日均线价格
    9. 今日收盘价格均线多头排列（MA5>MA10>MA20>MA30）
    10.今日MACD顶部左侧（今日红柱大于昨日红柱）
    """
    
    # 判断是否符合条件1（最近一次涨停最多是二板）
    last_limit_day = get_last_limit_day(stock_code, daily_bars, n)
    if last_limit_day == -1:
        return False
    
    daily_bars_last = daily_bars.loc[:last_limit_day].copy()
    limit_board_number = get_limit_board_number(stock_code, daily_bars_last)
    if limit_board_number == 0 or limit_board_number > 2:
        return False
    
    # 判断是否符合条件2
    if _is_exist_one_board(stock_code, daily_bars, m):
        return False
    
    focused_bars = get_daily_bars_by_date(daily_bars, start_date=last_limit_day, end_date=daily_bars.index[-1])
    
    # 判断是否符合条件3（通过focused_bars数量判断）
    if len(focused_bars) <= k:
        return False
    
    # 判断是否符合条件4（第2根K线与第1根K线的volume字段比值>=80%）
    volume_ratio = focused_bars['volume'].iloc[1] / focused_bars['volume'].iloc[0]
    if volume_ratio < 0.8:
        return False
    
    # 判断是否符合条件5（排除第1根K线后，成交量逐日递减）
    if not is_volume_decreasing(focused_bars.iloc[1:]):
        return False

    # 判断是否符合条件6（排除第1根K线后，日内震荡幅度处于涨停日价格的-2%~6%之间）
    limit_price = focused_bars.iloc[0]['close']
    lowest_price = focused_bars.iloc[1:]['low'].min()
    highest_price = focused_bars.iloc[1:]['high'].max()
    if lowest_price / limit_price - 1 < -0.03 or highest_price / limit_price - 1 > 0.06:
        return False

    # 判断是否符合条件7（日线收盘价不破涨停日价格）,误差0.005
    error = 0.005
    if focused_bars.iloc[1:]['close'].min() < limit_price * (1 - error):
        return False

    # 判断是否符合条件8（今日收盘价格高于30日均线价格）
    ma_price = get_ma(daily_bars=daily_bars, period=30)
    if focused_bars.iloc[-1]['close'] <= ma_price:
        return False

    # 判断是否符合条件9（均线多头排列（MA5>MA10>MA20>MA30））
    if not is_ma_bullish(daily_bars=daily_bars):
        return False

    # # 判断是否符合条件10（今日MACD柱大于昨日MACD柱））
    # macd_data = get_macd(daily_bars=daily_bars)
    # if macd_data.iloc[-1]['macd'] <= macd_data.iloc[-2]['macd']:
    #     return False
    
    return True


def _is_exist_last_first_board(stock_code: str, daily_bars: pd.DataFrame, n: int = 5) -> bool:
    """
    判断是否存在最近{n}个交易日内存在涨停板，且最近一次涨停是首板
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
        n: 最近{n}个交易日内存在涨停板，且最近一次涨停是首板
    Returns:
        bool: 是否符合条件，True表示符合，False表示不符合
    """
    debug(f"判断最近{n}个交易日中是否存在涨停板，且最近一次涨停是首板: {stock_code}")
    last_limit_day = get_last_limit_day(stock_code, daily_bars, n)
    if last_limit_day == -1:
        return False

    # 判断最近一次涨停是首板
    daily_bars_last = daily_bars.loc[:last_limit_day].copy()
    # debug(f"截断数据： {daily_bars_last}")
    if not is_first_board(stock_code, daily_bars_last):
        return False
    return True

def _is_exist_one_board(stock_code: str, daily_bars: pd.DataFrame, m: int = 10) -> bool:
    """
    判断是否存在最近{m}个交易日内存在一字板
    Args:
        stock_code: 股票代码
        daily_bars: 日K线数据框
        m: 最近{m}个交易日内存在一字板
    Returns:
        bool: 是否符合条件，True表示符合，False表示不符合
    """
    debug(f"判断是否存在最近{m}个交易日内存在一字板: {stock_code}")
    daily_bars_last = daily_bars.iloc[-m:].copy()
    # debug(f"截断数据： {daily_bars_last}")
    for index, row in daily_bars_last.iterrows():
        if is_one_board(stock_code, row['close'], row['preClose'], row['low'], row['high']):
            return True
    return False