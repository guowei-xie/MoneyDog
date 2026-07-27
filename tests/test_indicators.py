"""
指标类纯函数的金标准（golden-master）单测：量比、MACD、MACD 见顶/见底。

这些函数不依赖线上 DuckDB，可离线重复运行；用手工可验证的输入固定其数值行为，
为后续正确性/性能重构（T1/T2）提供回归防护。
"""
import math

import numpy as np
import pandas as pd
import pytest

from laboratory.multipleK import get_macd, is_macd_bottom, is_macd_top
from utils.volume_ratio import compute_volume_ratio_daily


def _df(volumes):
    return pd.DataFrame({"volume": volumes})


class TestVolumeRatioDaily:
    def test_basic_ratio_excludes_today(self):
        # 过去 5 日均量 = (100+100+100+100+100)/5 = 100；今日 200 → 量比 2.0
        df = _df([100, 100, 100, 100, 100, 200])
        assert compute_volume_ratio_daily(df, avg_days=5) == pytest.approx(2.0)

    def test_uses_only_prior_days_for_mean(self):
        # 过去 3 日 = [90, 100, 110] 均值 100；今日 150 → 1.5（今日不进均量）
        df = _df([10, 90, 100, 110, 150])
        assert compute_volume_ratio_daily(df, avg_days=3) == pytest.approx(1.5)

    def test_insufficient_history_returns_nan(self):
        # 需要 avg_days+1 行，这里只有 avg_days 行 → nan
        assert math.isnan(compute_volume_ratio_daily(_df([100, 100, 100]), avg_days=3))

    def test_zero_mean_volume_returns_nan(self):
        assert math.isnan(compute_volume_ratio_daily(_df([0, 0, 0, 0, 0, 100]), avg_days=5))

    def test_zero_today_volume_returns_nan(self):
        assert math.isnan(compute_volume_ratio_daily(_df([100, 100, 100, 100, 100, 0]), avg_days=5))

    def test_none_or_empty_returns_nan(self):
        assert math.isnan(compute_volume_ratio_daily(None, avg_days=5))
        assert math.isnan(compute_volume_ratio_daily(_df([]), avg_days=5))


class TestGetMacd:
    def test_constant_price_gives_zero_lines(self):
        df = pd.DataFrame({"close": [10.0] * 30})
        out = get_macd(df)
        assert out["dif"].abs().max() == pytest.approx(0.0, abs=1e-12)
        assert out["dea"].abs().max() == pytest.approx(0.0, abs=1e-12)
        assert out["macd"].abs().max() == pytest.approx(0.0, abs=1e-12)

    def test_matches_hand_computed_ema_recursion(self):
        # 小周期便于手算：alpha_fast=2/3, alpha_slow=2/5, alpha_signal=2/3, adjust=False
        df = pd.DataFrame({"close": [10.0, 11.0, 12.0]})
        out = get_macd(df, fast_period=2, slow_period=4, signal_period=2)
        # 见文件同目录推导：dif=[0, 0.266667, 0.515556]
        assert list(out["dif"]) == pytest.approx([0.0, 0.266667, 0.515556], abs=1e-5)
        # dea=[0, 0.177778, 0.402963]
        assert list(out["dea"]) == pytest.approx([0.0, 0.177778, 0.402963], abs=1e-5)
        # macd = 2*(dif-dea) = [0, 0.177778, 0.225185]
        assert list(out["macd"]) == pytest.approx([0.0, 0.177778, 0.225185], abs=1e-5)

    def test_identity_macd_equals_two_times_dif_minus_dea(self):
        rng = np.linspace(10, 20, 40) + np.sin(np.linspace(0, 6, 40))
        out = get_macd(pd.DataFrame({"close": rng}))
        assert list(out["macd"]) == pytest.approx(list(2 * (out["dif"] - out["dea"])), abs=1e-12)

    def test_does_not_mutate_input(self):
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
        get_macd(df)
        assert list(df.columns) == ["close"]


class TestMacdTopBottom:
    def test_top_true_when_hump_all_positive(self):
        # 顺序取 iloc[-1:-5:-1] → m1..m4 = 最近4根倒序；条件 m1<m2<m3>m4 且全>0
        # 造 macd 尾部 [.., m4, m3, m2, m1] = [1, 3, 2, 1] → m1=1<m2=2<m3=3>m4=1 ✅
        df = pd.DataFrame({"macd": [0.5, 1, 3, 2, 1]})
        assert is_macd_top(df) is True

    def test_top_false_when_any_nonpositive(self):
        df = pd.DataFrame({"macd": [-0.5, -1, 3, 2, 1]})  # m4=-1 → 不满足全>0
        assert is_macd_top(df) is False

    def test_top_false_when_insufficient(self):
        assert is_macd_top(pd.DataFrame({"macd": [1, 2, 3]})) is False

    def test_bottom_matches_implemented_condition(self):
        # 实现判定：m1>m2>m3>m4<m5 且全<0（注意与旧 docstring 描述不一致，以实现为准）
        # 尾部 [m5, m4, m3, m2, m1] = [-1, -5, -4, -3, -2]
        # m1=-2 > m2=-3 > m3=-4 > m4=-5 < m5=-1 ✅ 且全<0
        df = pd.DataFrame({"macd": [-1, -5, -4, -3, -2]})
        assert is_macd_bottom(df) is True

    def test_bottom_false_when_any_nonnegative(self):
        df = pd.DataFrame({"macd": [1, -5, -4, -3, -2]})  # m5=1 → 不满足全<0
        assert is_macd_bottom(df) is False

    def test_bottom_false_when_insufficient(self):
        assert is_macd_bottom(pd.DataFrame({"macd": [-1, -2, -3, -4]})) is False
