# MAST Data Analytics Engine

An end-to-end analytics engine for MAST time-series photometry (Kepler, K2, TESS). It:

- **measures exoplanet sizes** — removes instrument drift, finds transits with Box Least Squares, and fits the planet-to-star radius ratio two ways (the classical BLS box and a Physics-Informed Neural Network);
- **vets false positives** — odd/even, secondary-eclipse, transit-SNR and centroid-motion tests assign each candidate a disposition (planet candidate / needs review / likely false positive);
- **characterises variable stars** — a second SHO-PINN measures the coherence (quality factor Q) of stellar variability, with a dedicated Wolf-Rayet mission;
- **validates against the NASA Exoplanet Archive** and serves everything through an interactive Streamlit dashboard.

The repo ships with a populated results database (synthetic ground-truth targets + Kepler 8–17 + a TESS planet + real Wolf-Rayet stars), so the dashboard works the moment you launch it — no downloads. To analyse your own targets, run the pipeline against MAST. For the physics, validation numbers, and architecture, see [METHODOLOGY.md](METHODOLOGY.md).

## Run the dashboard (30 seconds, no downloads)

The dashboard reads the bundled database — it needs neither the internet nor PyTorch:

```bash
python -m venv .venv && .venv\Scripts\activate     # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Run the pipeline (measure your own targets)

Ingestion and PINN training need the heavier dependencies:

```bash
pip install -r requirements-pipeline.txt
python run_pipeline.py --synthetic --pinn                   # offline demo, known ground truth
python run_pipeline.py --targets Kepler-8 Kepler-10 --pinn  # real data from MAST
python run_pipeline.py --targets TOI-132 --mission TESS --pinn --vet   # + false-positive vetting
python run_pipeline.py --targets "HD 50896" --mission TESS --mode variability --pinn   # Wolf-Rayet coherence
python validate.py --range Kepler 8 17                      # compare vs NASA archive
```

Note: PyTorch requires Python ≤ 3.13 — on Windows use `py -3.12 -m venv .venv` if your default Python is newer. The dashboard itself has no such constraint.
