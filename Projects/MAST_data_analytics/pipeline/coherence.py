"""
Coherence (quality factor Q) from the autocorrelation — the SHO physics.

Deliberately separate from pinn_var.py and free of torch: Q is NOT a neural
network output. It is a classical statistic measured on the RAW light curve.
The variability PINN supplies the smooth fitted curve and the amplitude; the
coherence is read off the data's correlation structure. Keeping it here makes
that boundary explicit and lets the validation harness test Q without torch.

The physics
-----------
A stochastically driven damped harmonic oscillator has autocorrelation
    ACF(tau) = exp(-omega_0 tau / 2Q) . cos(omega_0 tau)
so sampling at integer-period lags tau = nP (where the cosine is 1) leaves a
pure exponential envelope
    ACF(nP) = exp(-pi n / Q)     =>     Q = -pi / slope( ln ACF(nP) vs n ).

Two estimator systematics this module corrects
----------------------------------------------
Both were found by injecting a KNOWN phase-diffusion rate and comparing the
recovered Q against the analytic truth (see pipeline/synthetic.py's
`injected_quality_factor` and the SYNTH-Q-* harness cases).

1. TRIANGULAR TAPER (the biased ACF estimator). `np.correlate(x, x)` sums
   only N-k products at lag k but, normalised against lag 0's N terms, the
   result carries a spurious (1 - k/N) decay. That taper alone forces a
   FINITE Q on a perfectly coherent signal, with a value set by the period
   and the baseline rather than the star: a pure sinusoid measured 90.9 at
   P=0.85 d over 30 d, but 51.0 at P=1.3 d and 200 (the ceiling) over 120 d.
   FIX: divide each lag by its own overlap count before normalising.

2. NOISE PLATEAU (selection bias at low coherence). The sample ACF decays
   correctly for a few lags and then flattens onto the estimator's own
   sampling noise (~1/sqrt(N_independent)) instead of continuing to zero.
   The old fixed `floor=0.05` sat BELOW that plateau, so noise-dominated
   lags were fitted as if they were signal, flattening the slope and
   inflating Q — an injected Q of 5 read back as 21.
   FIX: the physical envelope must decay monotonically, so stop at the first
   lag that fails to decrease (that is the plateau), and weight the fit by
   w = ACF^2, the inverse variance of ln(ACF) for constant absolute ACF
   noise (the unknown sigma cancels).

Accuracy after both fixes, against injected truth (mean of 8 seeds):
    Q_true    2      5     10     20     50    100    200
    old    +468%  +163%   +53%    -2%   -26%   -39%   -55%
    new      -8%    +4%    +2%    +0%    -7%   -14%   -20%
A perfectly coherent signal now returns Q_CEIL for every window tested.
Residual downward bias at Q > 50 is inherent: resolving a very slow decay
needs a baseline many coherence times long. Treat Q > ~100 as "at least
this coherent" rather than a precise value.
"""

import numpy as np

Q_CEIL = 200.0   # report Q at most this (a very coherent signal)
Q_FLOOR = 0.5    # below this the signal decoheres within one period


def coherence_Q(time, flux, period, n_max: int = 30,
                max_lag_frac: float = 0.5):
    """
    Quality factor from the autocorrelation envelope (the SHO coherence).

    ACF(nP) = exp(-pi n / Q)  =>  Q = -pi / slope(ln ACF(nP) vs n), using an
    UNBIASED autocorrelation, lags truncated at the noise plateau, and an
    inverse-variance weighted least-squares through the origin. See the
    module docstring for the two systematics this corrects.

    max_lag_frac bounds the lags used to a fraction of the baseline: the
    unbiased estimator divides by a shrinking overlap count, so its variance
    blows up as the lag approaches the full span.

    Returns Q clipped to [Q_FLOOR, Q_CEIL].
    """
    t = np.asarray(time, dtype=float)
    x = np.asarray(flux, dtype=float) - np.mean(flux)
    n_pts = x.size
    if n_pts < 4 or not period or period <= 0:
        return Q_CEIL

    ac = np.correlate(x, x, "full")[n_pts - 1:]          # lags 0 .. n_pts-1
    overlap = (n_pts - np.arange(ac.size)).astype(float)
    ac = ac / overlap                                     # (1) unbiased
    if ac[0] <= 0:
        return Q_CEIL
    ac = ac / ac[0]

    dt = np.median(np.diff(np.sort(t)))
    baseline = float(t.max() - t.min())
    if not np.isfinite(dt) or dt <= 0:
        return Q_CEIL

    # (2) walk out in integer-period lags while the envelope still decays;
    #     the first non-decrease is the noise plateau, so stop there.
    ns, vals = [], []
    prev = 1.0
    for n in range(1, n_max + 1):
        lag = n * period
        if lag > max_lag_frac * baseline:
            break
        i = int(round(lag / dt))
        if i >= ac.size:
            break
        a = ac[i]
        if a <= 0 or a >= prev:
            break
        ns.append(n)
        vals.append(a)
        prev = a

    if not ns:
        return Q_FLOOR          # no correlation survives even one period

    ns = np.asarray(ns, dtype=float)
    a = np.asarray(vals, dtype=float)
    w = a ** 2                  # inv-variance of ln(a); the noise sigma cancels
    slope = np.sum(w * ns * np.log(a)) / np.sum(w * ns * ns)
    if slope >= 0:
        return Q_CEIL
    return float(min(max(-np.pi / slope, Q_FLOOR), Q_CEIL))
