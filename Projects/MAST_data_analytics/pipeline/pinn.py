"""
Phase 4 — Physics-Informed Neural Network (IMPLEMENTED).

This file doubles as the study reference: every non-obvious choice is
annotated with WHY, including a real debugging episode (see the
DEBUGGING NOTE on FourierFeatures).

Design contract
---------------
- Input:  phase-folded time (BLS supplies period + t0 — the classical
          baseline SEEDS the ML layer: BLS finds the candidate, the
          PINN refines the profile and depth. Standard practice.)
- Output: predicted flux F(phase)
- Loss:   L_total = L_data + lambda * L_geometry + 0.1 * L_baseline
    L_data     = MSE(F_pred, F_obs)              (fit the photometry)
    L_geometry = (DeltaF_model - depth_param)^2  (transit geometry:
                 the network's realized depth must equal the explicit
                 physical depth parameter; sqrt(depth_param) IS the
                 PINN's Rp/R* estimate)
    L_baseline = mean((F_oot - 1)^2)             (out-of-transit flux
                 is normalized to exactly 1 — flux conservation)

Why fold first? A tanh MLP fed raw 30-day time cannot represent eight
razor-thin dips. Folding at the BLS period stacks all transits into
ONE feature.

Results go to the same SQL results table as BLS (method="pinn"); the
fitted curve is saved as plain arrays so the dashboard overlays it
WITHOUT importing torch (train offline, serve artifacts).
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class FourierFeatures(nn.Module):
    """
    Encode x -> [sin(pi k x), cos(pi k x)] for k = 1..n_freq.

    DEBUGGING NOTE — why this layer exists:
    v1 of this file fed normalized phase straight into the MLP. It
    trained to a loss plateau of 3.16e-6 — which is EXACTLY the MSE of
    a flat line that ignores the transit (in-transit fraction x
    depth^2 ~= 3.3e-6), far above the 4e-8 noise floor. Diagnosis:
    SPECTRAL BIAS. Small tanh networks learn low-frequency functions
    first, and a dip occupying ~4% of the input domain is a
    high-frequency feature they may never reach in finite training.
    The standard cure (Tancik et al. 2020, "Fourier Features Let
    Networks Learn High Frequency Functions...") is to lift the input
    into a basis of sinusoids so sharp features become linear
    combinations the network reaches immediately. Here the encoding is
    also PHYSICAL: folded phase is genuinely periodic, and sin/cos of
    phase respect that periodicity at the fold boundary.

    n_freq sets resolution: the finest feature representable is
    ~2/n_freq in x-units. Our transit core is ~0.03 x-units wide, so
    n_freq = 32 resolves it comfortably.
    """

    def __init__(self, n_freq: int = 32):
        super().__init__()
        k = torch.arange(1, n_freq + 1, dtype=torch.float32)
        self.register_buffer("k", k)

    def forward(self, x):
        # x: [N, 1]  ->  angles: [N, n_freq]  ->  features: [N, 2*n_freq]
        ang = np.pi * x * self.k
        return torch.cat([torch.sin(ang), torch.cos(ang)], dim=1)


class TransitNet(nn.Module):
    """
    FourierFeatures(32) -> Linear(64, 64) -> tanh -> Linear(64, 64)
    -> tanh -> Linear(64, 1).

    Q1 ANSWER (the shape question): the input is [N, 1] — N phase
    values, each its own row — and the output is [N, 1]. Linear layers
    apply the same affine map to EVERY row independently; PyTorch
    batches over dim 0. Feeding a flat [N] tensor is the classic trap:
    Linear would treat it as ONE sample with N features and crash.
    Internally the encoder widens each row from 1 to 64 Fourier
    features before the MLP sees it.

    The network predicts a RESIDUAL around the baseline (forward
    returns 1 + net(x)) so at initialization the model already sits at
    flux ~= 1 and training only has to learn the dip.

    depth_param is a LEARNABLE physical parameter trained jointly with
    the weights. Softplus keeps it strictly positive (a negative
    transit depth is unphysical). It receives gradient ONLY through
    L_geometry — watch it sit frozen during the lambda warmup in the
    training printout, then converge once the physics switches on.
    """

    def __init__(self, hidden: int = 64, n_freq: int = 32,
                 init_depth: float = 0.01):
        super().__init__()
        self.encode = FourierFeatures(n_freq)
        self.net = nn.Sequential(
            nn.Linear(2 * n_freq, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, 1),
        )
        # inverse-softplus so depth() starts at the given estimate:
        # softplus(raw) = log(1 + exp(raw))  =>  raw = log(expm1(d))
        raw0 = float(np.log(np.expm1(max(init_depth, 1e-5))))
        self.raw_depth = nn.Parameter(torch.tensor(raw0, dtype=torch.float32))

    def depth(self):
        return F.softplus(self.raw_depth)

    def forward(self, x):
        # x: [N, 1] normalized phase in [-1, 1]  ->  flux: [N, 1]
        return 1.0 + self.net(self.encode(x))


def physics_loss(f_pred, f_obs, model, grid_pred, in_transit, out_transit,
                 lam: float):
    """
    L_data + lambda * L_geometry + 0.1 * L_baseline.

    grid_pred:   model flux on a FIXED dense phase grid — constraints
                 are enforced on the continuous model, not just where
                 data points happen to fall.
    in_transit:  grid mask near phase 0 (the transit core).
    out_transit: grid mask well clear of the transit.
    """
    L_data = F.mse_loss(f_pred, f_obs)

    # Realized model depth: 1 - mean flux in the transit core. Mean,
    # not min(): min gives sparse, noisy gradients (only one grid
    # point receives signal per step).
    model_depth = 1.0 - grid_pred[in_transit].mean()
    L_geometry = (model_depth - model.depth()) ** 2

    # Flux conservation: out of transit the star sits at exactly 1.
    L_baseline = ((grid_pred[out_transit] - 1.0) ** 2).mean()

    return L_data + lam * L_geometry + 0.1 * L_baseline


def train_pinn(time, flux, period, t0, duration,
               epochs: int = 5000, lr: float = 2e-3,
               lam_max: float = 1.0, seed: int = 0, verbose: bool = True):
    """
    Fit the PINN to one target's flattened light curve.

    Inputs: numpy arrays + the BLS ephemeris (period, t0, duration in
    days).

    Returns (results, profile):
      results — dict with the same keys analyze.run_bls() produces
                (method="pinn"), ready for db.storage.save_result()
                unchanged.
      profile — (phase_days, flux_model) arrays of the fitted curve
                for torch-free dashboard overlay.
    """
    torch.manual_seed(seed)

    # ---- Phase-fold (days), then normalize to [-1, 1] -------------
    # tanh nets train poorly on large-magnitude inputs: activations
    # saturate and gradients vanish. The fold window is rescaled to
    # [-1, 1] to keep the network in its responsive regime.
    phase = ((np.asarray(time) - t0 + 0.5 * period) % period) - 0.5 * period
    x = (phase / (0.5 * period)).astype(np.float32)[:, None]   # [N, 1]
    y = np.asarray(flux, dtype=np.float32)[:, None]            # [N, 1]

    x_t = torch.from_numpy(x)
    y_t = torch.from_numpy(y)

    # ---- Fixed dense grid for the physics terms -------------------
    grid = torch.linspace(-1.0, 1.0, 2001).unsqueeze(1)        # [2001, 1]
    dur_x = duration / (0.5 * period)          # transit duration, x-units
    in_transit = (grid.abs() < 0.30 * dur_x).squeeze(1)   # transit core
    out_transit = (grid.abs() > 0.75 * dur_x).squeeze(1)  # clear of it

    model = TransitNet(init_depth=0.01)
    opt = torch.optim.Adam(model.parameters(), lr=lr)

    warmup = int(0.3 * epochs)   # let the data term shape the curve
    for epoch in range(epochs):  # first; then phase the physics in.
        # lambda schedule: 0 during warmup, then linear ramp to
        # lam_max. Enforcing geometry on an untrained curve would just
        # anchor the depth to garbage.
        if epoch < warmup:
            lam = 0.0
        else:
            lam = lam_max * (epoch - warmup) / max(epochs - warmup, 1)

        opt.zero_grad()
        f_pred = model(x_t)
        grid_pred = model(grid)
        loss = physics_loss(f_pred, y_t, model, grid_pred,
                            in_transit, out_transit, lam)
        loss.backward()
        opt.step()

        if verbose and (epoch + 1) % 1000 == 0:
            print(f"    epoch {epoch + 1:>5d}  loss={loss.item():.3e}  "
                  f"lam={lam:.2f}  depth={model.depth().item():.5f}")

    # ---- Extract physical results ---------------------------------
    with torch.no_grad():
        grid_pred = model(grid)
        model_depth = float(1.0 - grid_pred[in_transit].mean())
        flux_model = grid_pred.squeeze(1).numpy().astype(float)
    phase_days = grid.squeeze(1).numpy().astype(float) * 0.5 * period

    depth = max(model_depth, 0.0)
    results = {
        "method": "pinn",
        "period_days": float(period),      # ephemeris from BLS;
        "t0": float(t0),                   # the PINN refines the
        "duration_days": float(duration),  # profile and the depth.
        "depth": depth,
        "rp_over_rstar": float(np.sqrt(depth)),
    }
    return results, (phase_days, flux_model)
