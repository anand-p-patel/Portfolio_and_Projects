# Kepler Transit Analytics Engine

Measures exoplanet sizes from Kepler telescope light curves: it removes instrument drift, finds transit dips with Box Least Squares, then refines the planet-to-star radius ratio with a Physics-Informed Neural Network — all viewable in an interactive Streamlit dashboard. It ships with three synthetic ground-truth targets so the whole thing runs offline with no downloads. Run the two commands below to see it in action, then explore real Kepler targets with your own queries. For the physics, validation numbers, and architecture, see [METHODOLOGY.md](METHODOLOGY.md).

## Run it

```bash
python -m venv .venv && .venv\Scripts\activate     # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python run_pipeline.py --synthetic --pinn          # offline demo, no internet needed
streamlit run app.py                               # open the dashboard
```

Want real data? `python run_pipeline.py --targets Kepler-8 Kepler-10 --pinn` (downloads from the MAST archive).

Note: PyTorch requires Python ≤ 3.13 — on Windows use `py -3.12 -m venv .venv` if your default Python is newer.
