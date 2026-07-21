"""
Visualization layer.

All functions return matplotlib Figures (Streamlit renders them with
st.pyplot). Star imagery is SIMULATED FROM PHYSICS, not stock art:

- Colour: Planck blackbody spectrum at the star's catalogued Teff,
  integrated against the CIE 1931 colour-matching functions
  (multi-lobe Gaussian fits of Wyman, Sloan & Shirley 2013, JCGT),
  converted to sRGB.
- Limb darkening: linear law I(mu) = 1 - u(1 - mu) with u varying
  by temperature (representative Kepler-band values, cf. Claret &
  Bloemen 2011 tables).
- Planet silhouettes are drawn to scale from the pipeline's own
  measured Rp/R*. The image is the measurement.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

try:
    _trapz = np.trapezoid   # NumPy >= 2.0
except AttributeError:      # NumPy 1.x (np.trapz removed in 2.0)
    _trapz = np.trapz


# ----------------------------------------------------------------------
# Stellar physics -> display properties
# ----------------------------------------------------------------------

def _piecewise_gauss(x, mu, s1, s2):
    s = np.where(x < mu, s1, s2)
    return np.exp(-0.5 * ((x - mu) / s) ** 2)


def blackbody_rgb(teff):
    """
    sRGB colour of a blackbody at temperature `teff` (Kelvin).

    Planck spectral radiance over the visible band -> CIE XYZ via the
    Wyman/Sloan/Shirley (2013) analytic colour-matching fits -> sRGB
    (D65 matrix + gamma), normalised so the brightest channel is 1.
    """
    lam = np.linspace(380.0, 780.0, 200)          # nm
    lam_m = lam * 1e-9
    h, c, kB = 6.626e-34, 2.998e8, 1.381e-23
    B = (2 * h * c ** 2 / lam_m ** 5) / np.expm1(h * c / (lam_m * kB * teff))

    xbar = (1.056 * _piecewise_gauss(lam, 599.8, 37.9, 31.0)
            + 0.362 * _piecewise_gauss(lam, 442.0, 16.0, 26.7)
            - 0.065 * _piecewise_gauss(lam, 501.1, 20.4, 26.2))
    ybar = (0.821 * _piecewise_gauss(lam, 568.8, 46.9, 40.5)
            + 0.286 * _piecewise_gauss(lam, 530.9, 16.3, 31.1))
    zbar = (1.217 * _piecewise_gauss(lam, 437.0, 11.8, 36.0)
            + 0.681 * _piecewise_gauss(lam, 459.0, 26.0, 13.8))

    X, Y, Z = _trapz(B * xbar, lam), _trapz(B * ybar, lam), _trapz(B * zbar, lam)
    X, Z = X / Y, Z / Y
    M = np.array([[3.2406, -1.5372, -0.4986],
                  [-0.9689,  1.8758,  0.0415],
                  [0.0557, -0.2040,  1.0570]])
    rgb = M @ np.array([X, 1.0, Z])
    rgb = np.clip(rgb, 0, None)
    rgb = rgb / rgb.max()
    rgb = np.where(rgb <= 0.0031308, 12.92 * rgb,
                   1.055 * rgb ** (1 / 2.4) - 0.055)
    return np.clip(rgb, 0, 1)


def spectral_class(teff):
    """Harvard spectral class from effective temperature."""
    if teff is None:
        return "unknown"
    for limit, cls in [(30000, "O"), (10000, "B"), (7500, "A"),
                       (6000, "F"), (5200, "G"), (3700, "K")]:
        if teff >= limit:
            return cls
    return "M"


_LD_TEFF = np.array([3500, 4500, 5800, 7000, 8500, 10000])
_LD_U = np.array([0.75, 0.70, 0.60, 0.50, 0.42, 0.35])


def limb_darkening_u(teff):
    """Representative Kepler-band linear limb-darkening coefficient."""
    if teff is None:
        return 0.60
    return float(np.interp(teff, _LD_TEFF, _LD_U))


def _star_image(teff, scale=1.0, n=700, pad=1.25):
    """
    RGB image array of a limb-darkened star disc with a soft glow.
    `scale` sets the disc radius in axes units (1.0 fills the frame),
    used to draw stars at their relative physical sizes.
    """
    rgb = blackbody_rgb(teff if teff is not None else 5778.0)
    u = limb_darkening_u(teff)

    y, x = np.mgrid[-pad:pad:n * 1j, -pad:pad:n * 1j]
    r = np.sqrt(x ** 2 + y ** 2)
    img = np.zeros((n, n, 3))

    inside = r <= scale
    mu = np.sqrt(np.clip(1.0 - (r / scale) ** 2, 0.0, 1.0))
    inten = 1.0 - u * (1.0 - mu)
    img[inside] = inten[inside, None] * rgb[None, :]

    # slight white-hot core so the centre reads as brighter
    core = (inten ** 6)[..., None] * 0.25
    img[inside] = img[inside] * (1 - core[inside]) + core[inside]

    # soft coronal glow just beyond the limb
    outside = ~inside
    glow = np.exp(-(r - scale) / (0.06 * scale + 1e-9)) * 0.35
    img[outside] += glow[outside, None] * rgb[None, :]

    return np.clip(img, 0, 1)


# ----------------------------------------------------------------------
# Light-curve plots
# ----------------------------------------------------------------------

def _binned_median(phase, flux, nbins=80):
    bins = np.linspace(phase.min(), phase.max(), nbins + 1)
    idx = np.digitize(phase, bins) - 1
    bx, by = [], []
    for b in range(nbins):
        m = idx == b
        if m.sum() > 3:
            bx.append(0.5 * (bins[b] + bins[b + 1]))
            by.append(np.median(flux[m]))
    return np.array(bx), np.array(by)


def plot_light_curve(time, flux, title="Flattened light curve"):
    """Full detrended light curve."""
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(time, flux, ".", color="#1f77b4", markersize=1.5, alpha=0.6)
    ax.set_title(title)
    ax.set_xlabel("Time (days)")
    ax.set_ylabel("Normalized flux")
    pad = 3 * np.std(flux)
    ax.set_ylim(np.min(flux) - pad, np.max(flux) + pad)
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()
    return fig


def plot_raw_vs_flat(raw_time, raw_flux, time, flux):
    """Before/after panel — the ETL story in one image."""
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    axes[0].plot(raw_time, raw_flux / np.nanmedian(raw_flux), ".",
                 color="#888888", markersize=1.5, alpha=0.6)
    axes[0].set_title("Raw (instrument drift visible)")
    axes[0].set_ylabel("Relative flux")
    axes[1].plot(time, flux, ".", color="#1f77b4", markersize=1.5, alpha=0.6)
    axes[1].set_title("After Phase 2 detrend (transits isolated)")
    axes[1].set_xlabel("Time (days)")
    axes[1].set_ylabel("Normalized flux")
    for ax in axes:
        ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()
    return fig


def plot_folded(time, flux, period, t0, duration=None,
                model_phase=None, model_flux=None):
    """Phase-fold at the detected period so every transit stacks.
    If a fitted PINN profile is supplied (model_phase in days,
    model_flux), it is overlaid on the folded data."""
    phase = ((time - t0 + 0.5 * period) % period) - 0.5 * period
    order = np.argsort(phase)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(phase[order] * 24.0, flux[order], ".", color="#1f77b4",
            markersize=2, alpha=0.5, label="Folded data")

    bx, by = _binned_median(phase, flux, nbins=80)
    ax.plot(bx * 24.0, by, "-", color="#d62728", linewidth=2,
            label="Binned median")

    if model_phase is not None and model_flux is not None:
        ax.plot(np.asarray(model_phase) * 24.0, model_flux, "-",
                color="#2ca02c", linewidth=2, label="PINN model")

    if duration is not None:
        ax.set_xlim(-2.5 * duration * 24.0, 2.5 * duration * 24.0)
    ax.set_title(f"Phase-folded transit (P = {period:.4f} d)")
    ax.set_xlabel("Hours from mid-transit")
    ax.set_ylabel("Normalized flux")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="lower right")
    fig.tight_layout()
    return fig


def plot_folded_variability(time, flux, period, t0=None,
                            model_phase=None, model_flux=None):
    """
    Fold a variability light curve at its period and show the binned
    profile, with the SHO-PINN model overlaid (model_phase in days,
    centred). A coherent signal folds to a clean curve; an incoherent one
    folds nearly flat — the fold itself reflects the coherence.
    """
    t0 = float(time[0]) if t0 is None else t0
    phase = (((time - t0 + 0.5 * period) % period) - 0.5 * period) / period
    order = np.argsort(phase)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(phase[order], flux[order], ".", color="#1f77b4",
            markersize=2, alpha=0.4, label="Folded data")
    bx, by = _binned_median(phase, flux, nbins=80)
    ax.plot(bx, by, "-", color="#d62728", linewidth=2, label="Binned median")
    if model_phase is not None and model_flux is not None:
        ax.plot(np.asarray(model_phase) / period, model_flux, "-",
                color="#2ca02c", linewidth=2, label="SHO-PINN model")

    ax.set_title(f"Phase-folded variability (P = {period:.4f} d)")
    ax.set_xlabel("Phase")
    ax.set_ylabel("Normalized flux")
    ax.set_xlim(-0.5, 0.5)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="lower right")
    fig.tight_layout()
    return fig


def plot_folded_comparison(entries):
    """
    Overlay binned-median folded transits for several targets.
    entries: list of dicts with keys label, time, flux, period, t0,
    duration.
    """
    fig, ax = plt.subplots(figsize=(9, 5.5))
    cmap = plt.get_cmap("tab10")
    max_dur = max((e.get("duration") or 0.15) for e in entries)

    for i, e in enumerate(entries):
        phase = ((e["time"] - e["t0"] + 0.5 * e["period"]) % e["period"]
                 ) - 0.5 * e["period"]
        bx, by = _binned_median(phase, e["flux"], nbins=120)
        ax.plot(bx * 24.0, by, "-", linewidth=2, color=cmap(i % 10),
                label=e["label"])

    ax.set_xlim(-2.5 * max_dur * 24.0, 2.5 * max_dur * 24.0)
    ax.set_title("Folded transit comparison (binned medians)")
    ax.set_xlabel("Hours from mid-transit")
    ax.set_ylabel("Normalized flux")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="lower right")
    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------
# Simulated star imagery
# ----------------------------------------------------------------------

def render_star(teff, stellar_radius=None, name=None, scale=1.0, ax=None):
    """
    Simulated portrait of the host star: blackbody colour at its
    catalogued Teff, temperature-dependent limb darkening, soft glow.
    `scale` draws the disc at a relative size (for comparison
    galleries); pass `ax` to compose several stars in one figure.
    """
    img = _star_image(teff, scale=scale)
    if ax is None:
        fig, ax = plt.subplots(figsize=(5.5, 5.5))
        fig.patch.set_facecolor("black")
    else:
        fig = ax.figure
    ax.set_facecolor("black")
    ax.imshow(img, extent=[-1.25, 1.25, -1.25, 1.25], origin="lower")
    ax.set_aspect("equal")
    ax.axis("off")

    parts = []
    if name:
        parts.append(name)
    if teff is not None:
        parts.append(f"{spectral_class(teff)}-type")
        parts.append(f"{teff:.0f} K")
    else:
        parts.append("Teff unknown")
    parts.append(f"{stellar_radius:.2f} R\u2609" if stellar_radius is not None
                 else "R unknown")
    ax.set_title(" \u00b7 ".join(parts), color="white", fontsize=11)
    fig.tight_layout()
    return fig


def render_transit_scene(rp_over_rstar, teff=None):
    """
    Mid-transit scene: the simulated star (coloured by its Teff) with
    the planet silhouette drawn TO SCALE from the measured Rp/R*.
    """
    img = _star_image(teff, scale=1.0)
    fig, ax = plt.subplots(figsize=(6, 6))
    fig.patch.set_facecolor("black")
    ax.set_facecolor("black")
    ax.imshow(img, extent=[-1.25, 1.25, -1.25, 1.25], origin="lower")

    planet = plt.Circle((0.0, -0.2), rp_over_rstar, color="black", zorder=5)
    ax.add_patch(planet)

    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-1.25, 1.25)
    ax.set_aspect("equal")
    ax.axis("off")
    teff_txt = f" \u00b7 {teff:.0f} K" if teff is not None else ""
    ax.set_title(f"Transit to scale \u2014 Rp/R\u2605 = {rp_over_rstar:.3f}"
                 f"{teff_txt}", color="white", fontsize=12)
    fig.tight_layout()
    return fig
