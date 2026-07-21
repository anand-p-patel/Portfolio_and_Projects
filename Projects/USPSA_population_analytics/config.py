"""
Shared constants for the USPSA Population Analytics Engine.

Everything that more than one module needs to agree on lives here:
canonical division names, classification ordering, file paths, and
the color language used by the dashboard.
"""

from pathlib import Path

# Identity sentinel: entry scripts check this so that running from a folder
# where config.py belongs to a DIFFERENT project fails with a clear message
# instead of a confusing traceback (or, worse, the wrong app launching).
PROJECT_TAG = "uspsa-analytics"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_REPORTS_DIR = DATA_DIR / "raw_reports"      # YOUR live corpus: *.json (embedded) + *.txt (web report)
SAMPLE_REPORTS_DIR = DATA_DIR / "sample_reports"  # bundled reviewer matches (tracked); fallback when live corpus is empty
RAW_HTML_DIR = DATA_DIR / "raw_html"            # archival full results pages (regenerable, gitignored)
REFERENCE_DIR = DATA_DIR / "reference"
DISCOVERY_LOG = DATA_DIR / "discovery_log.jsonl"  # every JSON response the browser saw
MATCH_INDEX = DATA_DIR / "match_index.json"       # what we harvested + skip reasons
PENDING_MATCHES = DATA_DIR / "pending_matches.json"  # discover-only output the dashboard reads
SCRAPE_PROGRESS = DATA_DIR / "scrape_progress.json"  # live progress the dashboard polls

DEFAULT_SQLITE_URL = f"sqlite:///{(DATA_DIR / 'uspsa.db').as_posix()}"

CLASSIFIER_TITLES_CSV = REFERENCE_DIR / "classifier_titles.csv"

# ---------------------------------------------------------------------------
# Divisions
# ---------------------------------------------------------------------------
# The PractiScore "Web Report" text format spells divisions out in full
# (e.g. "Carry Optics", "Limited 10"). We normalize to these canonical names.
CANONICAL_DIVISIONS = [
    "Open",
    "Limited",
    "Limited Optics",
    "Carry Optics",
    "PCC",
    "Production",
    "Single Stack",
    "Revolver",
    "Limited 10",
]

# Lowercased alias -> canonical. Anything unmatched becomes "Other".
DIVISION_ALIASES = {
    "open": "Open", "op": "Open", "open division": "Open",
    "limited": "Limited", "ltd": "Limited", "limited division": "Limited",
    "limited optics": "Limited Optics", "lo": "Limited Optics",
    "limitedoptics": "Limited Optics",
    "carry optics": "Carry Optics", "co": "Carry Optics",
    "carryoptics": "Carry Optics", "production carry optics": "Carry Optics",
    "pcc": "PCC", "pistol caliber carbine": "PCC",
    "production": "Production", "prod": "Production",
    "single stack": "Single Stack", "ss": "Single Stack",
    "revolver": "Revolver", "rev": "Revolver",
    "limited 10": "Limited 10", "l10": "Limited 10", "lim10": "Limited 10",
}

# The four divisions the trend analysis focuses on by default.
FOCUS_DIVISIONS = ["Carry Optics", "Limited", "Limited Optics", "Open"]

# Short labels for tight chart legends.
DIVISION_SHORT = {
    "Carry Optics": "CO", "Limited": "LTD", "Limited Optics": "LO",
    "Open": "OPEN", "PCC": "PCC", "Production": "PROD",
    "Single Stack": "SS", "Revolver": "REV", "Limited 10": "L10",
    "Other": "OTHER",
}

# ---------------------------------------------------------------------------
# Classifications
# ---------------------------------------------------------------------------
CLASS_ORDER = ["GM", "M", "A", "B", "C", "D", "U"]  # best -> unclassified

def normalize_classification(raw: str) -> str:
    c = (raw or "").strip().upper()
    return c if c in CLASS_ORDER else "U"

def normalize_division(raw: str) -> str:
    return DIVISION_ALIASES.get((raw or "").strip().lower(), "Other")

# ---------------------------------------------------------------------------
# Dashboard color language (tuned for the dark "shot-timer" theme)
# ---------------------------------------------------------------------------
# One fixed hue per division so a division looks the same on every chart.
DIVISION_COLORS = {
    "Carry Optics": "#60a5fa",   # blue — the modern mainstream
    "Limited": "#f59e0b",        # brass amber — the old guard
    "Limited Optics": "#2dd4bf", # teal — the newcomer
    "Open": "#f87171",           # red — race guns
    "PCC": "#a78bfa",
    "Production": "#4ade80",
    "Single Stack": "#f472b6",
    "Revolver": "#fca5a5",
    "Limited 10": "#fdba74",
    "Other": "#475569",
}

# Classification "heat" ramp: GM hottest -> D coolest, U set apart in gray.
CLASS_COLORS = {
    "GM": "#fde047", "M": "#fbbf24", "A": "#fb923c",
    "B": "#f87171", "C": "#e11d48", "D": "#9f1239", "U": "#64748b",
}
