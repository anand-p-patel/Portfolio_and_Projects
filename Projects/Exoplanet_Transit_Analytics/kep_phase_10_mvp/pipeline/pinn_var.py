"""
Phase 7 (full) — Physics-Informed Neural Network for stellar variability.

Where the transit PINN (pinn.py) encodes an ALGEBRAIC geometry law, this
one encodes a DIFFERENTIAL law — the textbook PINN formulation. Wolf-Rayet
photometric variability (rotating wind structures / corotating interaction
regions, plus stochastic clumping) is well modelled by a stochastically
driven damped harmonic oscillator — the same physics as the celerite SHO
kernel (Foreman-Mackey et al. 2017). We fit a network f(t) to the light
curve and penalise the residual of the free SHO equation of motion:

        g'' + (ω₀/Q)·g'  +  ω₀²·g   ≈  0        (g = f − μ)

evaluated by AUTODIFF, with ω₀ and Q learned jointly with the weights:

    L = MSE(f, obs)  +  λ · mean(residual²)/ω₀⁴  +  amplitude anchor

Physical read-out:
    period P   = 2π/ω₀   (refines the Lomb-Scargle seed)
    quality Q  = coherence — LOW Q ⇒ heavily damped / stochastic wind;
                 HIGH Q ⇒ coherent pulsation or a clean rotational signal.

This is a *regularised* fit toward the free-oscillator solution (it reads
off the best-fit ω₀, Q), not a rigorous stochastic-ODE solve — the same
spirit as the transit PINN's soft geometry constraint. Results and a
folded model curve are stored as plain arrays so the dashboard serves
them without importing torch.
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from pipeline.pinn import FourierFeatures   # reuse the transit encoder

# Q is bounded to a sane astrophysical range for numerical stability; the
# exact high value is unimportant — what matters is that stochastic
# variability lands well below coherent variability.
Q_MIN, Q_MAX = 0.2, 60.0


class VarNet(nn.Module):
    """
    FourierFeatures(n_freq) -> MLP -> g(τ); f(τ) = μ + g(τ).

    Working in NORMALISED TIME τ = (t − t₀)/P_seed (one seed period ≈ 1
    unit) keeps the sinusoid at a low Fourier harmonic and the network in
    its responsive regime. μ (baseline), ω₀ (frequency) and Q (coherence)
    are learnable; ω₀ and Q are constrained positive/bounded.
    """

    def __init__(self, n_freq: int = 48, hidden: int = 64,
                 w0_init: float = 2.0 * np.pi, q_init: float = 8.0):
        super().__init__()
        self.encode = FourierFeatures(n_freq)
        self.net = nn.Sequential(
            nn.Linear(2 * n_freq, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, 1),
        )
        self.mu = nn.Parameter(torch.tensor(1.0))
        # softplus(raw_w0) = w0_init
        self.raw_w0 = nn.Parameter(
            torch.tensor(float(np.log(np.expm1(w0_init)))))
        # sigmoid-scaled Q in (Q_MIN, Q_MAX), initialised at q_init
        qf = (q_init - Q_MIN) / (Q_MAX - Q_MIN)
        self.raw_q = nn.Parameter(torch.tensor(float(np.log(qf / (1 - qf)))))

    def w0(self):
        return F.softplus(self.raw_w0)

    def Q(self):
        return Q_MIN + (Q_MAX - Q_MIN) * torch.sigmoid(self.raw_q)

    def g(self, tau):
        return self.net(self.encode(tau))

    def forward(self, tau):
        return self.mu + self.g(tau)


def _sho_residual(model, grid):
    """mean( (g'' + (ω₀/Q) g' + ω₀² g)² ) on a grid, via autodiff."""
    tau = grid.clone().requires_grad_(True)
    g = model.g(tau)
    g1 = torch.autograd.grad(g, tau, torch.ones_like(g),
                             create_graph=True)[0]
    g2 = torch.autograd.grad(g1, tau, torch.ones_like(g1),
                             create_graph=True)[0]
    w0, Q = model.w0(), model.Q()
    resid = g2 + (w0 / Q) * g1 + w0 ** 2 * g
    # normalise by ω₀⁴ so the residual scale is amplitude², comparable to
    # the data MSE and independent of the (learned) frequency — otherwise
    # the optimiser could shrink ω₀ just to cheapen the physics term.
    return (resid ** 2).mean() / (w0.detach() ** 4 + 1e-12)


def train_pinn_var(time, flux, period,
                   epochs: int = 4000, lr: float = 3e-3,
                   lam_max: float = 5.0, seed: int = 0, verbose: bool = True):
    """
    Fit the SHO-PINN to a variability light curve.

    Inputs: numpy arrays + the Lomb-Scargle period (days) as the seed.

    Returns (results, profile):
      results — dict (method="pinn_var") with period_days, amplitude,
                quality_factor, rms — ready for db.storage.save_result().
      profile — (phase_days, flux_model): the model folded at the
                recovered period into one cycle, for a torch-free overlay.
                A coherent (high-Q) signal folds to a clean curve; an
                incoherent (low-Q) one folds nearly flat — the picture IS
                the coherence.
    """
    torch.manual_seed(seed)
    t = np.asarray(time, dtype=float)
    y = np.asarray(flux, dtype=float)
    t0 = float(t.min())
    tau = ((t - t0) / period).astype(np.float32)[:, None]
    y_t = torch.from_numpy(y.astype(np.float32)[:, None])
    tau_t = torch.from_numpy(tau)

    grid = torch.linspace(float(tau.min()), float(tau.max()), 2000).unsqueeze(1)
    data_var = float(np.var(y))

    model = VarNet()
    opt = torch.optim.Adam(model.parameters(), lr=lr)

    warmup = int(0.3 * epochs)   # fit the data first, then phase physics in
    for epoch in range(epochs):
        lam = 0.0 if epoch < warmup else \
            lam_max * (epoch - warmup) / max(epochs - warmup, 1)

        opt.zero_grad()
        f_pred = model(tau_t)
        L_data = F.mse_loss(f_pred, y_t)
        L_phys = _sho_residual(model, grid)
        # keep the model's variance near the data's so it doesn't collapse
        # to the trivial flat solution that also zeroes the residual.
        model_var = model.g(grid).var()
        L_amp = (model_var - data_var) ** 2
        loss = L_data + lam * L_phys + 0.1 * L_amp
        loss.backward()
        opt.step()

        if verbose and (epoch + 1) % 1000 == 0:
            print(f"    epoch {epoch + 1:>5d}  loss={loss.item():.3e}  "
                  f"lam={lam:.2f}  P={2 * np.pi / float(model.w0()) * period:.4f}d"
                  f"  Q={float(model.Q()):.2f}")

    with torch.no_grad():
        w0 = float(model.w0())
        Q = float(model.Q())
        period_days = 2.0 * np.pi / w0 * period

        # Fold a dense model evaluation at the recovered period.
        tg = np.linspace(t.min(), t.max(), 4000)
        taug = ((tg - t0) / period).astype(np.float32)[:, None]
        fg = model(torch.from_numpy(taug)).squeeze(1).numpy()
        amplitude = float((np.percentile(fg, 95) - np.percentile(fg, 5)) / 2)

    ph = ((tg - t0) % period_days) / period_days           # phase 0..1
    order = np.argsort(ph)
    nb = 200
    edges = np.linspace(0, 1, nb + 1)
    idx = np.clip(np.digitize(ph[order], edges) - 1, 0, nb - 1)
    binned = np.array([fg[order][idx == b].mean() if np.any(idx == b)
                       else np.nan for b in range(nb)])
    centers = 0.5 * (edges[:-1] + edges[1:])
    ok = ~np.isnan(binned)
    phase_days = (centers[ok] - 0.5) * period_days          # centred, in days
    flux_model = binned[ok]

    results = {
        "method": "pinn_var",
        "period_days": float(period_days),
        "t0": t0,
        "duration_days": None,
        "depth": None,
        "rp_over_rstar": None,
        "amplitude": amplitude,
        "rms": float(np.std(y)),
        "quality_factor": float(Q),
    }
    return results, (phase_days, flux_model)
