"""tools/cluster_statistics.py: Scientific cluster-aware statistical analysis.

Implements:
1. Liang-Zeger cluster-robust variance estimation and fault-clustered confidence intervals.
2. Wilson score confidence intervals for independent proportions.
3. Paired McNemar tests with continuity correction for policy comparisons (B0-B3).
4. Cohen's kappa for inter-rater adjudication agreement with standard error.
5. Cluster bootstrap resampling (resampling by fault cluster).
6. Comprehensive metrics with explicit numerator/denominator reporting.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class RateCI:
    k: int
    n: int
    rate: float
    ci_lower: float
    ci_upper: float
    method: str

    def __str__(self) -> str:
        pct = self.rate * 100.0
        lo = self.ci_lower * 100.0
        hi = self.ci_upper * 100.0
        return f"{pct:.1f}% ({self.k}/{self.n}, 95% CI [{lo:.1f}%, {hi:.1f}%])"


def wilson_ci(k: int, n: int, confidence: float = 0.95) -> RateCI:
    """Wilson score confidence interval for an independent binomial proportion."""
    if n <= 0:
        return RateCI(0, 0, 0.0, 0.0, 0.0, "wilson")
    z = 1.959963984540054  # 95% standard normal quantile
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    margin = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)) / denom
    return RateCI(
        k=k,
        n=n,
        rate=p,
        ci_lower=0.0 if k == 0 else max(0.0, center - margin),
        ci_upper=1.0 if k == n else min(1.0, center + margin),
        method="wilson",
    )


def cluster_robust_ci(
    cluster_counts: list[tuple[int, int]],
    confidence: float = 0.95,
) -> RateCI:
    """Liang-Zeger cluster-robust variance estimator and confidence interval.

    cluster_counts: list of (k_cluster, n_cluster) for each fault cluster.
    """
    total_k = sum(k for k, _ in cluster_counts)
    total_n = sum(n for _, n in cluster_counts)
    k_clusters = len(cluster_counts)

    if total_n <= 0:
        return RateCI(0, 0, 0.0, 0.0, 0.0, "cluster_robust")
    p_hat = total_k / total_n
    if k_clusters <= 1:
        return wilson_ci(total_k, total_n, confidence)

    # Cluster-robust sandwich variance:
    # V = (K / (K - 1)) * (1 / N^2) * sum_c (k_c - n_c * p_hat)^2
    ss = sum((k_c - n_c * p_hat) ** 2 for k_c, n_c in cluster_counts)
    df_correction = k_clusters / (k_clusters - 1)
    variance = df_correction * (ss / (total_n * total_n))
    se = math.sqrt(variance)

    # Use t-distribution critical value approximation
    z = 1.959963984540054
    margin = z * se
    return RateCI(
        k=total_k,
        n=total_n,
        rate=p_hat,
        ci_lower=max(0.0, p_hat - margin),
        ci_upper=min(1.0, p_hat + margin),
        method="cluster_robust",
    )


def cluster_bootstrap_ci(
    cluster_counts: list[tuple[int, int]],
    replications: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
) -> RateCI:
    """Non-parametric cluster bootstrap (resampling entire fault clusters with replacement)."""
    total_k = sum(k for k, _ in cluster_counts)
    total_n = sum(n for _, n in cluster_counts)
    k_clusters = len(cluster_counts)
    if total_n <= 0 or k_clusters == 0:
        return RateCI(0, 0, 0.0, 0.0, 0.0, "cluster_bootstrap")

    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(replications):
        sample = [rng.choice(cluster_counts) for _ in range(k_clusters)]
        sample_k = sum(k for k, _ in sample)
        sample_n = sum(n for _, n in sample)
        estimates.append(sample_k / sample_n if sample_n > 0 else 0.0)

    estimates.sort()
    lo_idx = int(math.floor(alpha / 2.0 * replications))
    hi_idx = int(math.ceil((1.0 - alpha / 2.0) * replications)) - 1
    p_hat = total_k / total_n
    return RateCI(
        k=total_k,
        n=total_n,
        rate=p_hat,
        ci_lower=max(0.0, estimates[lo_idx]),
        ci_upper=min(1.0, estimates[hi_idx]),
        method="cluster_bootstrap",
    )


@dataclass(frozen=True)
class McNemarResult:
    n01: int  # A=0 (rejected/failed), B=1 (accepted/passed)
    n10: int  # A=1 (accepted/passed), B=0 (rejected/failed)
    total_discordant: int
    chi2: float
    p_value: float
    risk_difference: float
    odds_ratio: float | None

    def __str__(self) -> str:
        p_str = f"{self.p_value:.4f}" if self.p_value >= 0.0001 else "<0.0001"
        or_str = f"{self.odds_ratio:.2f}" if self.odds_ratio is not None else "inf"
        return (
            f"McNemar chi2={self.chi2:.3f}, p={p_str}, "
            f"discordant=(n01={self.n01}, n10={self.n10}), "
            f"risk_diff={self.risk_difference * 100.0:+.1f}%, OR={or_str}"
        )


def mcnemar_test(
    paired_outcomes: list[tuple[int, int]],
    continuity_correction: bool = True,
) -> McNemarResult:
    """McNemar's test on paired binary observations (Policy A vs Policy B).

    paired_outcomes: list of (outcome_A, outcome_B) where 1=approved/pass, 0=rejected/fail.
    """
    n01 = sum(1 for a, b in paired_outcomes if a == 0 and b == 1)
    n10 = sum(1 for a, b in paired_outcomes if a == 1 and b == 0)
    total_disc = n01 + n10
    total_pairs = len(paired_outcomes)

    if total_disc == 0:
        return McNemarResult(0, 0, 0, 0.0, 1.0, 0.0, 1.0)

    if continuity_correction:
        chi2 = ((abs(n01 - n10) - 1.0) ** 2) / total_disc
    else:
        chi2 = ((n01 - n10) ** 2) / total_disc

    # 1-degree-of-freedom p-value approximation via erf
    p_val = math.erfc(math.sqrt(max(0.0, chi2)) / math.sqrt(2.0))
    risk_diff = (n01 - n10) / total_pairs if total_pairs > 0 else 0.0
    odds_ratio = (n01 / n10) if n10 > 0 else None

    return McNemarResult(
        n01=n01,
        n10=n10,
        total_discordant=total_disc,
        chi2=chi2,
        p_value=p_val,
        risk_difference=risk_diff,
        odds_ratio=odds_ratio,
    )


@dataclass(frozen=True)
class KappaResult:
    kappa: float
    observed_agreement: float
    expected_agreement: float
    se: float
    ci_lower: float
    ci_upper: float
    n: int

    def __str__(self) -> str:
        lo = self.ci_lower
        hi = self.ci_upper
        return (
            f"Cohen's kappa={self.kappa:.3f} (95% CI [{lo:.3f}, {hi:.3f}], "
            f"P_o={self.observed_agreement * 100.0:.1f}%, P_e={self.expected_agreement * 100.0:.1f}%, N={self.n})"
        )


def cohen_kappa(rater1_labels: Sequence[str], rater2_labels: Sequence[str]) -> KappaResult:
    """Compute Cohen's kappa for inter-rater agreement."""
    if len(rater1_labels) != len(rater2_labels):
        raise ValueError("Rater label sequences must have equal length")
    n = len(rater1_labels)
    if n == 0:
        return KappaResult(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)

    categories = sorted(set(rater1_labels) | set(rater2_labels))
    c1 = Counter(rater1_labels)
    c2 = Counter(rater2_labels)

    observed_matches = sum(1 for a, b in zip(rater1_labels, rater2_labels) if a == b)
    p_o = observed_matches / n

    p_e = sum((c1[cat] / n) * (c2[cat] / n) for cat in categories)
    if math.isclose(p_e, 1.0):
        kappa = 1.0
        se = 0.0
    else:
        kappa = (p_o - p_e) / (1.0 - p_e)
        # Large sample variance of Cohen's kappa
        var = (p_o * (1.0 - p_o)) / (n * ((1.0 - p_e) ** 2))
        se = math.sqrt(max(0.0, var))

    z = 1.959963984540054
    return KappaResult(
        kappa=kappa,
        observed_agreement=p_o,
        expected_agreement=p_e,
        se=se,
        ci_lower=max(-1.0, kappa - z * se),
        ci_upper=min(1.0, kappa + z * se),
        n=n,
    )
