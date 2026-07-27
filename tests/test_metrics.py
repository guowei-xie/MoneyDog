"""
账户收益类风险指标纯函数的金标准单测（laboratory.metrics）。

重点验证：'active' 口径剔除纯空仓静止日后，标准差不再被 0% 收益稀释；
以及夏普/索提诺/年化波动的手算数值。全部离线、不依赖 DuckDB。
"""
import math

import numpy as np
import pytest

from laboratory.metrics import build_risk_return_series, compute_return_risk_metrics

ANN = math.sqrt(252)


class TestBuildRiskReturnSeries:
    def test_all_basis_includes_flat_cash_days(self):
        ta = [100, 100, 100, 110, 110]
        sc = [0, 0, 1, 1, 0]
        r, n = build_risk_return_series(ta, sc, basis="all")
        # 相邻日收益共 4 个（含多处 0）
        assert n == 4
        assert list(r) == pytest.approx([0.0, 0.0, 0.1, 0.0])

    def test_active_basis_drops_idle_cash_days(self):
        ta = [100, 100, 100, 110, 110]
        sc = [0, 0, 1, 1, 0]
        # idx1: 空仓且 0% → 剔除; idx2: 持仓(0%)保留; idx3: 持仓+波动保留; idx4: 空仓且 0% → 剔除
        r, n = build_risk_return_series(ta, sc, basis="active")
        assert n == 2
        assert list(r) == pytest.approx([0.0, 0.1])

    def test_active_std_not_diluted_below_all(self):
        ta = [100, 100, 100, 110, 110]
        sc = [0, 0, 1, 1, 0]
        r_all, _ = build_risk_return_series(ta, sc, basis="all")
        r_act, _ = build_risk_return_series(ta, sc, basis="active")
        # 剔除 0% 静止日后标准差更大（不再被稀释），故夏普会更保守
        assert r_act.std(ddof=1) > r_all.std(ddof=1)

    def test_fully_invested_series_identical_for_both_basis(self):
        # 每日均持仓 → active 与 all 应完全一致（保证不改变常在场策略的口径）
        ta = [100, 101, 99, 103]
        sc = [1, 1, 1, 1]
        r_all, n_all = build_risk_return_series(ta, sc, basis="all")
        r_act, n_act = build_risk_return_series(ta, sc, basis="active")
        assert n_all == n_act == 3
        assert list(r_all) == pytest.approx(list(r_act))


class TestComputeReturnRiskMetrics:
    def test_hand_computed_sharpe_and_volatility(self):
        returns = [0.01, -0.02, 0.03]
        m = compute_return_risk_metrics(returns, rf_daily=0.0, ann_factor=ANN)
        # mean=0.0066667, std(ddof=1)=0.0251661
        assert m["mean"] == pytest.approx(0.0066667, abs=1e-6)
        assert m["std"] == pytest.approx(0.0251661, abs=1e-6)
        assert m["annual_volatility"] == pytest.approx(0.0251661 * ANN, abs=1e-5)
        assert m["sharpe"] == pytest.approx(0.0066667 / 0.0251661 * ANN, abs=1e-4)

    def test_sortino_uses_only_downside(self):
        returns = [0.05, -0.01, -0.03]
        m = compute_return_risk_metrics(returns, rf_daily=0.0, ann_factor=ANN)
        downside_std = np.std([-0.01, -0.03], ddof=1)  # 仅 <0 的收益
        expected = (np.mean(returns) - 0.0) / downside_std * ANN
        assert m["sortino"] == pytest.approx(expected, abs=1e-6)

    def test_single_sample_gives_nan_std_based_metrics(self):
        m = compute_return_risk_metrics([0.01], rf_daily=0.0, ann_factor=ANN)
        assert math.isnan(m["std"])
        assert math.isnan(m["sharpe"])
        assert math.isnan(m["annual_volatility"])

    def test_zero_volatility_series_gives_nan_sharpe(self):
        m = compute_return_risk_metrics([0.0, 0.0, 0.0], rf_daily=0.0, ann_factor=ANN)
        assert math.isnan(m["sharpe"])
        assert math.isnan(m["annual_volatility"])
