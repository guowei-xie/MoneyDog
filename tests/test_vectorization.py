"""
T2-3 向量化改动的等价性测试：确保向量化实现与原逐行/逐窗口实现结果完全一致。

覆盖：
- singleK.is_limit_series 对比逐行 is_limit
- multipleK.get_ma5_bottom / get_ma5_top 对比原 rolling.apply(lambda) 参考实现
全部离线，不依赖 DuckDB。
"""
import numpy as np
import pandas as pd

from laboratory.singleK import is_limit, is_limit_series
from laboratory.multipleK import get_ma5_bottom, get_ma5_top


class TestIsLimitSeries:
    def _check_matches_scalar(self, code, closes, pres, limit_type):
        s = is_limit_series(code, pd.Series(closes), pd.Series(pres), limit_type=limit_type)
        for i, (c, p) in enumerate(zip(closes, pres)):
            expected = (not pd.isna(p)) and is_limit(code, c, p, limit_type=limit_type)
            # is_limit_series 对 NaN preClose 自然给 False，与 (notna and is_limit) 一致
            assert bool(s.iloc[i]) == bool(expected), (code, i, c, p, limit_type)

    def test_up_main_board(self):
        closes = [11.0, 10.98, 10.5, 11.0, 9.0]
        pres = [10.0, 10.0, 10.0, 10.0, 10.0]
        self._check_matches_scalar("000001.SZ", closes, pres, "up")

    def test_up_chinext_20pct(self):
        closes = [12.0, 11.9, 11.98, 10.0]
        pres = [10.0, 10.0, 10.0, 10.0]
        self._check_matches_scalar("300750.SZ", closes, pres, "up")

    def test_down_main_board(self):
        closes = [9.0, 9.02, 9.5, 8.5]
        pres = [10.0, 10.0, 10.0, 10.0]
        self._check_matches_scalar("000001.SZ", closes, pres, "down")

    def test_nan_preclose_is_false(self):
        s = is_limit_series("000001.SZ", pd.Series([11.0, 11.0]), pd.Series([np.nan, 10.0]))
        assert bool(s.iloc[0]) is False
        assert bool(s.iloc[1]) is True


def _ma5_left_right_ref(df, left_count, right_count, left_sign, right_sign):
    """用原 rolling.apply(lambda) 逻辑复算 is_ma5_bottom/top，作为等价性金标准。"""
    d = df.copy()
    ma5 = d["close"].rolling(window=5, min_periods=5).mean()
    diff = ma5.diff()
    left = (left_sign(diff)).rolling(window=left_count, min_periods=left_count).apply(
        lambda x: x.all() and not x.isna().any(), raw=False
    ).shift(1).fillna(0).astype(bool)
    right = (right_sign(diff)).rolling(window=right_count, min_periods=right_count).apply(
        lambda x: x.all() and not x.isna().any(), raw=False
    ).shift(-right_count).fillna(0).astype(bool)
    return (left & right).astype(bool)


class TestMa5BottomTopEquivalence:
    def _df(self, seed):
        rng = np.random.default_rng(seed)
        return pd.DataFrame({"close": np.cumsum(rng.normal(0, 1, size=45)) + 100})

    def test_bottom_matches_reference(self):
        for seed in range(20):
            df = self._df(seed)
            ref = _ma5_left_right_ref(df, 5, 1, lambda x: x < 0, lambda x: x > 0)
            out = get_ma5_bottom(df, left_count=5, right_count=1)["is_ma5_bottom"]
            assert out.tolist() == ref.tolist(), f"bottom seed={seed}"

    def test_top_matches_reference(self):
        for seed in range(20):
            df = self._df(seed)
            ref = _ma5_left_right_ref(df, 5, 1, lambda x: x > 0, lambda x: x < 0)
            out = get_ma5_top(df, left_count=5, right_count=1)["is_ma5_top"]
            assert out.tolist() == ref.tolist(), f"top seed={seed}"

    def test_bottom_wider_right_window(self):
        for seed in range(10):
            df = self._df(seed + 100)
            ref = _ma5_left_right_ref(df, 5, 5, lambda x: x < 0, lambda x: x > 0)
            out = get_ma5_bottom(df, left_count=5, right_count=5)["is_ma5_bottom"]
            assert out.tolist() == ref.tolist(), f"bottom-wide seed={seed}"
