"""
Phase 7 (full) — Physics-Informed Neural Network for stellar variability.

Wolf-Rayet photometric variability (rotating wind structures / corotating
interaction regions, plus stochastic clumping) is well modelled by a
stochastically driven damped harmonic oscillator (SHO) — the same physics
as the celerite SHO kernel (Foreman-Mackey et al. 2017). Two quantities
characterise it: the period, and the QUALITY FACTOR Q — the coherence.
LOW Q ⇒ heavily damped / stochastic wind; HIGH Q ⇒ coherent pulsation or
a clean rotational signal.

What this module does
---------------------
1. A small PINN (VarNet) fits a smooth, continuous model f(t) to the light
   curve. Periodic Fourier features respect the fold boundary and denoise;
   the fitted curve is served to the dashboard (torch-free arrays).
2. Q is measured from the SHO's autocorrelation signature: a damped
   oscillator's ACF envelope decays as exp(-ω₀ τ / 2Q) = exp(-π n / Q) at
   integer-period lags n, so  Q = -π / slope( ln|ACF(nP)| vs n ).

DESIGN NOTE — why not an ODE-residual training loss?
    The textbook PINN move is to put the free-SHO residual
    (g'' + (ω₀/Q)g' + ω₀²g) in the loss and learn ω₀, Q. On this problem
    that is numerically unstable: the free frequency ω₀ drifts, and the
    trivial flat solution g=0 zeroes the residual, collapsing the fitted
    amplitude. The residual is also amplitude-degenerate, so it fights the
    data term. The autocorrelation is the same physics in integral form
    (the SHO's ACF *is* exp(-ω₀τ/2Q)cos ω₀τ) but robust to noise and free
    of the collapse mode — so the PINN fits the signal and the SHO physics
    reads Q off its correlation structure. (Compare the DEBUGGING NOTE in
    pinn.py: the transit PINN carries a similar hard-won correction.)

Results and a folded model curve are stored as plain arrays so the
dashboard serves them without importing torch.
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from pipeline.pinn import FourierFeatures   # reuse the transit encoder

Q_CEIL = 200.0   # report Q at most this (a very coherent signal)


class VarNet(nn.Module):
    """
    FourierFeatures(n_freq) -> MLP -> g(τ);  f(τ) = μ + g(τ).

    Time is normalised to τ = (t − t₀)/P_seed (one seed period ≈ 1 unit),
    so the variability sits at a low Fourier harmonic and the network
    stays in its responsive regime. μ (baseline) is learnable; a modest
    n_freq acts as a low-pass that fits the oscillation and its
    slow envelope but rejects white noise.
    """

    def __init__(self, n_freq: int = 24, hidden: int = 64):
        super().__init__()
        self.encode = FourierFeatures(n_freq)
        self.net = nn.Sequential(
            nn.Linear(2 * n_freq, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, 1),
        )
        self.mu = nn.Parameter(torch.tensor(1.0))

    def g(self, tau):
        return self.net(self.encode(tau))

    def forward(self, tau):
        return self.mu + self.g(tau)


def coherence_Q(time, flux, period, n_max: int = 15, floor: float = 0.05):
    """
    Quality factor from the autocorrelation envelope (the SHO coherence).

    ACF(nP) ≈ exp(-π n / Q)  ⇒  Q = -π / slope(ln ACF(nP) vs n).
    Robust to white noise (which decorrelates away from lag 0) and needs
    no derivatives. Returns Q capped at Q_CEIL.
    """
    t = np.asarray(time, dtype=float)
    x = np.asarray(flux, dtype=float) - np.mean(flux)
    ac = np.correlate(x, x, "full")
    ac = ac[ac.size // 2:]
    ac /= ac[0]
    dt = np.median(np.diff(np.sort(t)))

    ns, lns = [], []
    for n in range(1, n_max + 1):
        i = int(round(n * period / dt))
        if i < ac.size and ac[i] > floor:
            ns.append(n)
            lns.append(np.log(ac[i]))
    if len(ns) < 2:
        return Q_CEIL
    ns = np.asarray(ns, dtype=float)
    lns = np.asarray(lns, dtype=float)
    slope = np.sum(ns * lns) / np.sum(ns * ns)   # least squares through origin
    if slope >= 0:
        return Q_CEIL
    return float(min(-np.pi / slope, Q_CEIL))


def train_pinn_var(time, flux, period,
                   epochs: int = 2500, lr: float = 3e-3,
                   n_freq: int = 24, seed: int = 0, verbose: bool = True):
    """
    Fit the variability PINN and characterise the signal.

    Inputs: numpy arrays + the Lomb-Scargle period (days) as the seed.

    Returns (results, profile):
      results — dict (method="pinn_var") with period_days, amplitude,
                quality_factor, rms — ready for db.storage.save_result().
      profile — (phase_days, flux_model): the model folded at the period
                into one cycle, for a torch-free overlay. A coherent
                (high-Q) signal folds to a clean curve; an incoherent one
                folds nearly flat — the picture reflects the coherence.
    """
    torch.manual_seed(seed)
    t = np.asarray(time, dtype=float)
    y = np.asarray(flux, dtype=float)
    t0 = float(t.min())
    tau = ((t - t0) / period).astype(np.float32)[:, None]
    x_t = torch.from_numpy(tau)
    y_t = torch.from_numpy(y.astype(np.float32)[:, None])
    data_std = float(np.std(y))

    model = VarNet(n_freq=n_freq)
    opt = torch.optim.Adam(model.parameters(), lr=lr)

    for epoch in range(epochs):
        opt.zero_grad()
        f_pred = model(x_t)
        L_data = F.mse_loss(f_pred, y_t)
        # anchor the model's spread to the data's so the fit tracks the
        # variability rather than settling on the flat mean.
        L_amp = (model.g(x_t).std() / (data_std + 1e-12) - 1.0) ** 2
        loss = L_data + L_amp
        loss.backward()
        opt.step()
        if verbose and (epoch + 1) % 1000 == 0:
            print(f"    epoch {epoch + 1:>5d}  loss={loss.item():.3e}")

    # Coherence from the DATA autocorrelation (measuring it on the
    # over-smoothed model would erase the very incoherence we quantify).
    Q = coherence_Q(t, y, period)

    with torch.no_grad():
        tg = np.linspace(t.min(), t.max(), 4000)
        fg = model(torch.from_numpy(
            ((tg - t0) / period).astype(np.float32)[:, None])).squeeze(1).numpy()
    amplitude = float((np.percentile(fg, 95) - np.percentile(fg, 5)) / 2)

    # Fold the smooth model into one cycle for the dashboard overlay.
    ph = ((tg - t0) % period) / period
    nb = 200
    edges = np.linspace(0.0, 1.0, nb + 1)
    idx = np.clip(np.digitize(ph, edges) - 1, 0, nb - 1)
    binned = np.array([fg[idx == b].mean() if np.any(idx == b) else np.nan
                       for b in range(nb)])
    centers = 0.5 * (edges[:-1] + edges[1:])
    ok = ~np.isnan(binned)
    phase_days = (centers[ok] - 0.5) * period
    flux_model = binned[ok]

    results = {
        "method": "pinn_var",
        "period_days": float(period),
        "t0": t0,
        "duration_days": None,
        "depth": None,
        "rp_over_rstar": None,
        "amplitude": amplitude,
        "rms": float(np.std(y)),
        "quality_factor": float(Q),
    }
    return results, (phase_days, flux_model)
