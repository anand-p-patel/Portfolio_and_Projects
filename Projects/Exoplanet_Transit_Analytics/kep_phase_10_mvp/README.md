# Kepler Transit Analytics Engine

Measures exoplanet sizes from Kepler and TESS light curves: it removes instrument drift, finds transit dips with Box Least Squares, and measures the planet-to-star radius ratio two ways — the classical BLS box and a Physics-Informed Neural Network — all viewable in an interactive Streamlit dashboard. The repo ships with a populated results database (synthetic targets + Kepler 8–17 + a TESS planet), so the dashboard works the moment you launch it — no downloads. To measure your own targets, run the pipeline against the MAST archive. For the physics, validation numbers, and architecture, see [METHODOLOGY.md](METHODOLOGY.md).

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
python run_pipeline.py --targets TOI-132 --mission TESS --pinn
python validate.py --range Kepler 8 17                      # compare vs NASA archive
```

Note: PyTorch requires Python ≤ 3.13 — on Windows use `py -3.12 -m venv .venv` if your default Python is newer. The dashboard itself has no such constraint.
