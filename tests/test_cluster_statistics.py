"""Unit tests for tools/cluster_statistics.py."""

import pytest
from tools.cluster_statistics import (
    wilson_ci,
    cluster_robust_ci,
    cluster_bootstrap_ci,
    mcnemar_test,
    cohen_kappa,
)


def test_wilson_ci_bounds():
    ci = wilson_ci(10, 100)
    assert ci.rate == 0.10
    assert 0.05 < ci.ci_lower < 0.10
    assert 0.10 < ci.ci_upper < 0.18
    assert ci.k == 10 and ci.n == 100


def test_wilson_ci_extremes():
    zero = wilson_ci(0, 50)
    assert zero.rate == 0.0
    assert zero.ci_lower == 0.0
    assert zero.ci_upper > 0.0

    one = wilson_ci(50, 50)
    assert one.rate == 1.0
    assert one.ci_lower < 1.0
    assert one.ci_upper == 1.0


def test_cluster_robust_ci_computes():
    # 3 clusters of size 10
    clusters = [(2, 10), (3, 10), (1, 10)]
    ci = cluster_robust_ci(clusters)
    assert ci.k == 6
    assert ci.n == 30
    assert pytest.approx(ci.rate, 0.01) == 0.20
    assert ci.ci_lower < ci.rate < ci.ci_upper
    assert "cluster_robust" in ci.method


def test_cluster_bootstrap_ci_bounds():
    clusters = [(5, 10), (4, 10), (6, 10), (5, 10)]
    ci = cluster_bootstrap_ci(clusters, replications=500, seed=123)
    assert ci.k == 20
    assert ci.n == 40
    assert 0.35 <= ci.ci_lower <= 0.50
    assert 0.50 <= ci.ci_upper <= 0.65


def test_mcnemar_identical_policies():
    # Identical policies -> 0 discordant pairs -> p=1.0
    paired = [(1, 1)] * 20 + [(0, 0)] * 30
    res = mcnemar_test(paired)
    assert res.total_discordant == 0
    assert res.p_value == 1.0
    assert res.risk_difference == 0.0


def test_mcnemar_significant_discordance():
    # 25 pairs where A rejects (0) and B accepts (1), 2 pairs where A accepts and B rejects
    paired = [(0, 1)] * 25 + [(1, 0)] * 2 + [(1, 1)] * 30 + [(0, 0)] * 30
    res = mcnemar_test(paired)
    assert res.n01 == 25
    assert res.n10 == 2
    assert res.total_discordant == 27
    assert res.chi2 > 15.0
    assert res.p_value < 0.001


def test_cohen_kappa_perfect_agreement():
    r1 = ["correct", "incorrect", "insecure", "correct"]
    r2 = ["correct", "incorrect", "insecure", "correct"]
    res = cohen_kappa(r1, r2)
    assert res.kappa == 1.0
    assert res.observed_agreement == 1.0
    assert res.ci_lower > 0.99


def test_cohen_kappa_partial_agreement():
    r1 = ["correct", "correct", "incorrect", "insecure"]
    r2 = ["correct", "incorrect", "incorrect", "insecure"]
    res = cohen_kappa(r1, r2)
    assert 0.5 < res.kappa < 1.0
    assert res.observed_agreement == 0.75
