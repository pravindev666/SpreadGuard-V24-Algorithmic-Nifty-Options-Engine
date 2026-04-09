"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         NIFTY SpreadGuard V2024 — "The Multi-Layer Sniper"  Backtest             ║
║         Backtest engine: 2015–present                                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  V16 Upgrades over V15 (7 New Levers):                                      ║
║                                                                              ║
║  V16-A: Full OTM Ladder (150/200/300/400/500/600/700)                       ║
║         — Each OTM level tied to precise ATR/VIX/Safety gates               ║
║         — 150/200/300 only fire in ultra-calm (ATR<130, VIX<12)             ║
║         — 400 OTM Narrow Condor for calm regimes                            ║
║                                                                              ║
║  V16-B: Regime-Adaptive Premium Optimiser                                   ║
║         — Premiums now scale with OTM level, not just tier name             ║
║         — Butterfly (150/200 OTM) replaces removed ATM-spread               ║
║         — All near-OTM tiers gated by ATR<130 + score=0 hard lock          ║
║                                                                              ║
║  V16-C: Butterfly / Iron Fly tier (150 OTM ±)                               ║
║         — Ultra-calm only: ATR<130, VIX<12, Score=0, Safety≥80%            ║
║         — 1.5× standard spread width (300 pts)                              ║
║         — 50% TP, 0.75× size, 5-day hold max                               ║
║                                                                              ║
║  V16-D: 400 OTM Narrow Condor                                               ║
║         — ATR<140, VIX<16, Score≤1, Safety≥80%                             ║
║         — Higher premium (220 pts) for calm regimes                         ║
║                                                                              ║
║  V16-E: Wide Condor (600+600 OTM)                                           ║
║         — New option for ATR 180–200 (below High-ATR threshold)            ║
║         — Lower premium but far safer legs                                  ║
║                                                                              ║
║  V16-F: Dual OTM reporting per trade                                        ║
║         — CSV now records both short & long strike OTM for analysis         ║
║                                                                              ║
║  V16-G: Rolling regime tracker                                              ║
║         — Monthly regime labels appended to output CSV                      ║
║                                                                              ║
║  All V15 features preserved (V15-A through V15-E).                          ║
║  All V13 features preserved (V13-A through V13-F).                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Usage:
    python backtest_spreadguard_v16.py
    python backtest_spreadguard_v16.py --start 2015-01-01 --end 2024-12-31
    python backtest_spreadguard_v16.py --compare        # vs V15 results CSV
    python backtest_spreadguard_v16.py --year 2024      # single-year drill
"""

import argparse
import warnings
from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.stats import norm

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# V16 CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

VERSION = "V2024"
QTY_PER_LOT = 65


SLIPPAGE = {
    "Aggressive":       -5,
    "Normal":           -5,
    "Cautious":         -8,
    "Bear-Call":        -10,
    "Tuesday-LV":       -5,
    "Wednesday-MW":     -7,
    "Monday-RW":        -7,
    "Friday-SNP":       -8,
    "VIX-Collapse":     -8,
    "Near-VC":          -8,
    "Condor-BP":        -5,
    "Condor-BC":        -10,
    "Thursday-EXP":     -5,
    "HighATR-Cautious": -8,
    # V16 new tiers
    "Butterfly":        -12,   # tight strikes = wider bid/ask
    "NarrowCondor-BP":  -8,
    "NarrowCondor-BC":  -8,
    "WideCondor-BP":    -5,
    "WideCondor-BC":    -5,
}

PREMIUM_BASE = {
    "Aggressive":       100,
    "Normal":            60,
    "Cautious":          40,
    "Bear-Call":         60,
    "Tuesday-LV":        40,
    "Wednesday-MW":      50,
    "Monday-RW":         45,
    "Friday-SNP":        42,
    "VIX-Collapse":     100,
    "Near-VC":           80,
    "Condor-BP":         80,
    "Condor-BC":         80,
    "Thursday-EXP":      35,
    "HighATR-Cautious":  30,
    # V16 new tiers
    "Butterfly":        180,   # 150 OTM short straddle/strangle wings
    "NarrowCondor-BP":  110,
    "NarrowCondor-BC":  110,
    "WideCondor-BP":     50,
    "WideCondor-BC":     50,
}

OTM_DIST_BASE = {
    "Aggressive":       500,
    "Normal":           600,
    "Cautious":         700,
    "Bear-Call":        600,
    "Tuesday-LV":       700,
    "Wednesday-MW":     650,
    "Monday-RW":        680,
    "Friday-SNP":       640,
    "VIX-Collapse":     700,
    "Near-VC":          700,
    "Condor-BP":        500,
    "Condor-BC":        500,
    "Thursday-EXP":     600,
    "HighATR-Cautious": 750,
    "Butterfly":        200,   # V16-C: ±200 OTM iron fly
    "NarrowCondor-BP":  400,   # V16-D
    "NarrowCondor-BC":  400,
    "WideCondor-BP":    600,   # V16-E
    "WideCondor-BC":    600,
}

SAFETY_FLOOR = {
    "Aggressive":        75.0,
    "Normal":            75.0,
    "Cautious":          72.0,
    "Bear-Call":         75.0,
    "Tuesday-LV":        70.0,
    "Wednesday-MW":      73.0,
    "Monday-RW":         73.0,
    "Friday-SNP":        90.0,   # V15 tightened from 88
    "VIX-Collapse":      65.0,
    "Near-VC":           68.0,
    "Condor-BP":         75.0,
    "Condor-BC":         75.0,
    "Thursday-EXP":      85.0,
    "HighATR-Cautious":  78.0,
    "Butterfly":         80.0,   # V16-C: tight floor for near-ATM
    "NarrowCondor-BP":   80.0,
    "NarrowCondor-BC":   80.0,
    "WideCondor-BP":     75.0,
    "WideCondor-BC":     75.0,
}

TP_MULTIPLIER = {
    "DEFAULT": 0.35,  # V2024 Quick TP
    "Aggressive":        0.70,
    "Normal":            0.60,
    "Cautious":          0.60,
    "Bear-Call":         0.70,
    "Tuesday-LV":        0.65,
    "Wednesday-MW":      0.62,
    "Monday-RW":         0.62,
    "Friday-SNP":        0.58,
    "VIX-Collapse":      0.70,
    "Near-VC":           0.65,
    "Condor-BP":         0.60,
    "Condor-BC":         0.60,
    "Thursday-EXP":      0.50,
    "HighATR-Cautious":  0.55,
    "Butterfly":         0.50,   # V16-C: exit early (near-ATM risk)
    "NarrowCondor-BP":   0.60,
    "NarrowCondor-BC":   0.60,
    "WideCondor-BP":     0.62,
    "WideCondor-BC":     0.62,
}

# ATR gates per tier
ATR_GATE = {
    "Aggressive":       150,
    "Normal":           180,
    "Cautious":         180,
    "Bear-Call":        200,
    "Tuesday-LV":       180,
    "Wednesday-MW":     180,
    "Monday-RW":        160,
    "Friday-SNP":       130,
    "VIX-Collapse":    9999,
    "Near-VC":         9999,
    "Condor-BP":        180,
    "Condor-BC":        180,
    "Thursday-EXP":     100,
    "HighATR-Cautious": 240,   # only fires ABOVE 180
    "Butterfly":        130,   # V16-C: ultra-calm only
    "NarrowCondor-BP":  140,   # V16-D
    "NarrowCondor-BC":  140,
    "WideCondor-BP":    200,   # V16-E
    "WideCondor-BC":    200,
}

HOLD_DAYS           = 7
HOLD_DAYS_THURS     = 1
HOLD_DAYS_FRI       = 6
HOLD_DAYS_BUTTERFLY = 5       # V16-C: shorter hold for near-ATM
SPREAD_WIDTH        = 200.0
BUTTERFLY_WIDTH     = 300.0   # V16-C: wider wing

CONDOR_VIX_MIN      = 12.0
CONDOR_VIX_MAX      = 20.0
CONDOR_ATR_MIN      = 120.0
CONDOR_ATR_MAX      = 180.0   # V15 tightened from 220

VIX_SPIKE_SUPPRESS  = 4.0     # V15-D (was 5.0 in V13)
ATR_NORM_REF        = 150.0
ADAPTIVE_OTM_MIN    = 0.90
ADAPTIVE_OTM_MAX    = 1.10

HIGH_ATR_MIN        = 180.0   # V15-A
HIGH_ATR_MAX        = 240.0

# V16-C Butterfly ATR ceiling
BUTTERFLY_ATR_MAX   = 130.0
BUTTERFLY_VIX_MAX   = 12.0

# V16-D Narrow Condor
NARROW_CONDOR_ATR_MAX = 140.0
NARROW_CONDOR_VIX_MAX = 16.0

# V16-E Wide Condor
WIDE_CONDOR_ATR_MIN = 160.0
WIDE_CONDOR_ATR_MAX = 200.0

WEEKLY_RISK_LIMIT        = 600.0
WEEKLY_RISK_LIMIT_NORMAL = 420.0
WEEKLY_RISK_LIMIT_ELEV   = 300.0
WEEKLY_RISK_LIMIT_HIGH   = 200.0   # V15-E


# V19-A: Dynamic VIX Bands (from V18)
VIX_BAND_NORMAL_MULT   = 1.15
VIX_BAND_NORMAL_CAP    = 20.0

# V19-B: Velocity Sensor
VELOCITY_THRESHOLD     = 3.5

def vix_bands(vix_20d_avg):
    avg = vix_20d_avg if not np.isnan(vix_20d_avg) else 15.0
    return min(avg * VIX_BAND_NORMAL_MULT, VIX_BAND_NORMAL_CAP)


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_data(nifty_path="data/nifty_daily.csv", vix_path="data/vix_daily.csv"):
    try:
        nifty = pd.read_csv(nifty_path, parse_dates=["date"])
        vix   = pd.read_csv(vix_path,   parse_dates=["date"])
    except FileNotFoundError as e:
        print(f"⚠  Data file not found: {e}")
        print("   Place nifty_daily.csv and vix_daily.csv in the data/ folder.")
        print("   Format: date, open, high, low, close")
        return None, None
    nifty.columns = nifty.columns.str.lower().str.strip()
    vix.columns   = vix.columns.str.lower().str.strip()
    return (nifty.sort_values("date").reset_index(drop=True),
            vix.sort_values("date").reset_index(drop=True))


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────────────────

def compute_flags(nifty: pd.DataFrame, vix: pd.DataFrame) -> pd.DataFrame:
    df = pd.merge(nifty, vix[["date", "close"]], on="date", how="inner",
                  suffixes=("", "_vix"))
    df["prev_close"]     = df["close"].shift(1)
    df["prev_close_vix"] = df["close_vix"].shift(1)

    df["vix_chg_1d"] = (df["close_vix"] - df["prev_close_vix"]) / df["prev_close_vix"] * 100
    df["vix_2d_chg"] = df["close_vix"].pct_change(2) * 100
    df["vix_5d_std"] = df["close_vix"].rolling(5).std()

    # ATR (EWM — matches TradingView RMA)
    df["tr"] = np.maximum(
        (df["high"] - df["low"]).abs(),
        np.maximum(
            (df["high"] - df["prev_close"]).abs(),
            (df["low"]  - df["prev_close"]).abs(),
        ),
    )
    df["atr"] = df["tr"].ewm(alpha=1 / 14, adjust=False).mean()

    # Trend indicators
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["vix_20d_avg"] = df["close_vix"].rolling(20).mean()

    df["roc5"]  = df["close"].pct_change(5) * 100
    df["roc1"]  = df["close"].pct_change(1) * 100
    df["velocity"] = df["roc1"].abs() + df["roc1"].shift(1).abs() + df["roc1"].shift(2).abs()

    # Bollinger band width
    df["bb_mid"] = df["close"].rolling(20).mean()
    df["bb_std"] = df["close"].rolling(20).std()
    df["bbw"]    = (4 * df["bb_std"]) / df["bb_mid"] * 100
    df["bbw_avg"]= df["bbw"].rolling(20).mean()

    # Average daily gap
    df["avg_gap"] = (df["close"] - df["prev_close"]).abs() / df["prev_close"] * 100
    df["avg_gap_10"] = df["avg_gap"].rolling(10).mean()

    # Open gap (for V15 gap guard)
    df["open_gap_pct"] = (df["open"] - df["prev_close"]).abs() / df["prev_close"] * 100

    # Friday quiet check (ATR 3 days ago < 150)
    df["atr_3d_ago"] = df["atr"].shift(3)
    df["fri_quiet"]  = df["atr_3d_ago"] < 150

    df["day_of_week"] = df["date"].dt.dayofweek  # 0=Mon, 4=Fri

    # Danger score (0–6)
    df["score"] = (
        (df["close_vix"] > 18).astype(int) +
        (df["vix_chg_1d"] > 15).astype(int) +
        (df["atr"] > 200).astype(int) +
        (df["roc5"].abs() > 2.0).astype(int) +
        (df["bbw"] > df["bbw_avg"] * 1.2).astype(int) +
        (df["avg_gap_10"] > 0.8).astype(int)
    ).clip(0, 6)

    df["week_key"] = df["date"].dt.isocalendar().year.astype(str) + "_" + \
                     df["date"].dt.isocalendar().week.astype(str).str.zfill(2)

    # Regime label (for V16-G)
    df["regime"] = np.where(df["close_vix"] < 12, "ultra-calm",
                   np.where(df["close_vix"] < 16, "normal",
                   np.where(df["close_vix"] < 20, "elevated",
                   np.where(df["close_vix"] < 25, "high", "crisis"))))

    return df.dropna(subset=["atr", "ema20"]).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# CORE CALCULATIONS
# ─────────────────────────────────────────────────────────────────────────────

def norm_cdf(x: float) -> float:
    return float(norm.cdf(x))


def compute_safety(row: pd.Series, otm_dist: float, hold_days: int = 7) -> float:
    c   = row["close"]
    atr = row["atr"]
    if c <= 0 or atr <= 0:
        return 0.0
    dv = atr / c
    z  = (otm_dist / c) / (dv * np.sqrt(hold_days))
    return (1.0 - (1.0 - norm_cdf(z)) * 2.0) * 100.0


def adaptive_otm(base_otm: float, atr: float) -> int:
    ratio  = max(ADAPTIVE_OTM_MIN, min(ADAPTIVE_OTM_MAX, atr / ATR_NORM_REF))
    result = base_otm * ratio
    return int(round(result / 50) * 50)


def weekly_heat_cap(vix: float, atr: float, score: int) -> float:
    if atr > HIGH_ATR_MIN:
        return WEEKLY_RISK_LIMIT_HIGH
    if atr > 150 or vix > 16:
        return WEEKLY_RISK_LIMIT_ELEV
    if vix < 12 and score == 0:
        return WEEKLY_RISK_LIMIT
    return WEEKLY_RISK_LIMIT_NORMAL


def lot_size(safety: float, tier: str) -> float:
    fixed_75 = {"Near-VC", "Thursday-EXP", "Wednesday-MW", "Monday-RW",
                "Friday-SNP", "HighATR-Cautious", "Butterfly",
                "NarrowCondor-BP", "WideCondor-BP"}
    if tier in fixed_75:
        return 0.75
    if safety > 95:
        return 1.5
    if safety > 85:
        return 1.0
    return 0.75


# ─────────────────────────────────────────────────────────────────────────────
# TRADE SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

def simulate_trade(
    hold_slice: pd.DataFrame,
    entry_close: float,
    tier: str,
    otm_dist: float,
    is_bear_call: bool,
    hold_days: int,
) -> tuple[float, int]:
    """Simulate one spread leg. Returns (pnl_pts, days_held)."""
    premium  = PREMIUM_BASE.get(tier, 60)
    tp_pts   = premium * TP_MULTIPLIER.get(tier, 0.60)
    slip     = SLIPPAGE.get(tier, -5)
    is_butterfly = "Butterfly" in tier

    # Strike for this leg
    sw = BUTTERFLY_WIDTH if is_butterfly else SPREAD_WIDTH
    if is_bear_call:
        short_strike = entry_close + otm_dist
        breach_price = short_strike
    else:
        short_strike = entry_close - otm_dist
        breach_price = short_strike

    entry_net = premium + slip

    for day_idx, (_, bar) in enumerate(hold_slice.iterrows(), start=1):
        price = bar["close"]

        # Realistic TP approximation (time decay + directional movement)
        time_decay = day_idx / hold_days
        if is_bear_call:
            dist_moved = price - entry_close
        else:
            dist_moved = entry_close - price
        
        # dist_factor: positive means market moved towards strike (against us)
        dist_factor = max(0, dist_moved) / otm_dist 
        remaining_pct = max(0.0, 1.0 - time_decay + dist_factor)
        decay_pct = 1.0 - remaining_pct
        if decay_pct >= TP_MULTIPLIER.get(tier, 0.60):
            return round(tp_pts + slip, 1), day_idx

        # Partial exit: Day 3, 50% of OTM distance moved
        if day_idx == 3:
            if is_bear_call and price > entry_close + otm_dist * 0.5:
                return round(entry_net * 0.85, 1), day_idx
            if not is_bear_call and price < entry_close - otm_dist * 0.5:
                return round(entry_net * 0.85, 1), day_idx

        # Breach check
        if is_bear_call and price >= breach_price:
            loss = -(sw - premium) + slip
            return round(loss, 1), day_idx
        if not is_bear_call and price <= breach_price:
            loss = -(sw - premium) + slip
            return round(loss, 1), day_idx

    # Held to expiry — win
    return round(tp_pts + slip, 1), len(hold_slice)


# ─────────────────────────────────────────────────────────────────────────────
# V16 BACKTEST ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def run_v2024_backtest(
    df: pd.DataFrame,
    start_date: str = None,
    end_date: str   = None,
) -> pd.DataFrame:

    if start_date:
        df = df[df["date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["date"] <= pd.Timestamp(end_date)]
    df = df.reset_index(drop=True)

    trades = []

    # Week-level deduplication sets
    used_layers     = set()  # V2024 Sniper Layers (Mon/Wed/Fri)
    used_tuesday    = set()
    used_thursday   = set()
    used_condor     = set()
    used_butterfly  = set()

    circuit_breaker_until = pd.Timestamp("2000-01-01")
    consecutive_losses    = 0

    for i, row in df.iterrows():
        if i + 1 >= len(df):
            break

        curr_date = row["date"]
        if curr_date <= circuit_breaker_until:
            continue

        vix    = row["close_vix"]
        atr    = row["atr"]
        score  = int(row["score"])
        vix_chg= row["vix_chg_1d"]
        roc1   = row["roc1"]
        week   = row["week_key"]
        dow    = row["day_of_week"]   # 0=Mon … 4=Fri
        regime = row["regime"]

        # ── Hard blocks ──────────────────────────────────────────────────────

        vix_20      = row.get("vix_20d_avg", 15.0)
        velocity    = row.get("velocity", 0.0)
        vix_ceiling = vix_bands(vix_20)

        # ── V19 Mod ───────────────────────────────────────────────────────
        if velocity > VELOCITY_THRESHOLD and score >= 1:
            # Velocity block applies to credit spreads during non-ultra-calm
            v19_velocity_blocked = True
        else:
            v19_velocity_blocked = False

        if vix >= 25:
            continue
        if vix_chg > VIX_SPIKE_SUPPRESS:   # V15-D
            continue
        if row["open_gap_pct"] > 0.8:       # V15 gap guard
            continue

        vix_5d_std = row["vix_5d_std"] if not np.isnan(row["vix_5d_std"]) else 99
        vix_stb    = vix_5d_std < 1.5

        bull_bias = (row["ema20"] > row["ema50"]) and (row["close"] > row["ema50"]) and (row["roc5"] > 0.5)
        bear_bias = (row["ema20"] < row["ema50"]) and (row["close"] < row["ema50"]) and (row["roc5"] < -0.5)
        neut_bias = not bull_bias and not bear_bias

        dual_ok   = (vix < vix_ceiling) and (atr < 200)
        ultra_calm= (score == 0) and (vix < 12) and (atr < 150) and vix_stb

        weekly_cap = weekly_heat_cap(vix, atr, score)
        weekly_heat = sum(
            t.get("Risk", 0)
            for t in trades
            if t.get("Week") == week
        )

        entry_tier: str = None
        otm_dist: float = 0.0

        # ── PRIORITY WATERFALL ───────────────────────────────────────────────

        # 1. VIX-Collapse (>15% 2-day VIX drop)
        vc_2d = row["vix_2d_chg"]
        if (vc_2d < -15 and score < 3 and vix < vix_ceiling and atr < 250):
            adj = 700.0
            s   = compute_safety(row, adj)
            if s >= SAFETY_FLOOR["VIX-Collapse"]:
                entry_tier, otm_dist = "VIX-Collapse", adj

        # 2. Near-VIX-Collapse (10–15% drop)
        if not entry_tier and -15 <= vc_2d < -10 and score < 3 and vix < vix_ceiling:
            adj = 700.0
            s   = compute_safety(row, adj)
            if s >= SAFETY_FLOOR["Near-VC"]:
                entry_tier, otm_dist = "Near-VC", adj

        # 3. V16-C: Butterfly (ultra-calm only, 150–200 OTM)
        if (not entry_tier
                and week not in used_butterfly
                and ultra_calm
                and atr <= BUTTERFLY_ATR_MAX
                and vix <= BUTTERFLY_VIX_MAX
                and score == 0):
            otm_b = 200.0
            s_put = compute_safety(row, otm_b, HOLD_DAYS_BUTTERFLY)
            s_call= compute_safety(row, otm_b, HOLD_DAYS_BUTTERFLY)
            if s_put >= SAFETY_FLOOR["Butterfly"] and s_call >= SAFETY_FLOOR["Butterfly"]:
                entry_tier, otm_dist = "Butterfly", otm_b

        # 4. Thursday Expiry (1-day)
        if (not entry_tier
                and week not in used_thursday
                and dow == 3
                and score <= 1
                and vix < 14
                and atr < 100
                and vix < vix_ceiling):
            adj = adaptive_otm(OTM_DIST_BASE["Thursday-EXP"], atr)
            s   = compute_safety(row, adj, HOLD_DAYS_THURS)
            if s >= SAFETY_FLOOR["Thursday-EXP"]:
                entry_tier, otm_dist = "Thursday-EXP", float(adj)

        # 5. Friday Sniper (V13-A, floor 90% in V15)
        if (not entry_tier
                and (week + "_fri") not in used_layers
                and dow == 4
                and score <= 1
                and vix <= 14
                and atr <= 130
                and dual_ok):
            adj = adaptive_otm(OTM_DIST_BASE["Friday-SNP"], atr)
            s   = compute_safety(row, adj, HOLD_DAYS_FRI)
            if s >= SAFETY_FLOOR["Friday-SNP"]:
                entry_tier, otm_dist = "Friday-SNP", float(adj)

        # 6. Monday Recovery (V12-D)
        if (not entry_tier
                and (week + "_mon") not in used_layers and not v19_velocity_blocked
                and dow == 0
                and score <= 1
                and vix < 16
                and atr <= 160
                and dual_ok):
            adj = adaptive_otm(OTM_DIST_BASE["Monday-RW"], atr)
            s   = compute_safety(row, adj)
            if s >= SAFETY_FLOOR["Monday-RW"]:
                entry_tier, otm_dist = "Monday-RW", float(adj)

        # 7. Wednesday Midweek (V12-A)
        if (not entry_tier
                and (week + "_wed") not in used_layers and not v19_velocity_blocked
                and dow == 2
                and score <= 1
                and vix < vix_ceiling
                and atr <= 180):
            adj = adaptive_otm(OTM_DIST_BASE["Wednesday-MW"], atr)
            s   = compute_safety(row, adj)
            if s >= SAFETY_FLOOR["Wednesday-MW"]:
                entry_tier, otm_dist = "Wednesday-MW", float(adj)

        # 8. V16-D: Narrow Condor (400 OTM, calm regime)
        if (not entry_tier
                and week not in used_condor
                and neut_bias
                and score <= 1
                and atr <= NARROW_CONDOR_ATR_MAX
                and vix <= NARROW_CONDOR_VIX_MAX
                and vix_stb):
            otm_n = 400.0
            s_bp  = compute_safety(row, otm_n)
            s_bc  = compute_safety(row, otm_n)
            if s_bp >= SAFETY_FLOOR["NarrowCondor-BP"] and s_bc >= SAFETY_FLOOR["NarrowCondor-BC"]:
                entry_tier, otm_dist = "NarrowCondor", otm_n

        # 9. Iron Condor (V15 tightened ATR gate 180)
        if (not entry_tier
                and (week + "_wed") not in used_layers
                and neut_bias
                and score <= 2
                and CONDOR_VIX_MIN <= vix <= CONDOR_VIX_MAX
                and CONDOR_ATR_MIN <= atr <= CONDOR_ATR_MAX
                and vix_stb
                and dual_ok):
            put_leg  = float(450 if roc1 > 0.3 else 500)
            call_leg = float(450 if roc1 < -0.3 else 500)
            put_leg  = float(adaptive_otm(put_leg,  atr))
            call_leg = float(adaptive_otm(call_leg, atr))
            s_bp     = compute_safety(row, put_leg)
            s_bc     = compute_safety(row, call_leg)
            if s_bp >= SAFETY_FLOOR["Condor-BP"] and s_bc >= SAFETY_FLOOR["Condor-BC"]:
                entry_tier, otm_dist = "CONDOR", put_leg

        # 10. V16-E: Wide Condor (600+600, for ATR 160–200)
        if (not entry_tier
                and (week + "_wed") not in used_layers
                and neut_bias
                and score <= 2
                and WIDE_CONDOR_ATR_MIN <= atr <= WIDE_CONDOR_ATR_MAX
                and vix < 20
                and vix_stb):
            otm_w = 600.0
            s_bp  = compute_safety(row, otm_w)
            s_bc  = compute_safety(row, otm_w)
            if s_bp >= SAFETY_FLOOR["WideCondor-BP"] and s_bc >= SAFETY_FLOOR["WideCondor-BC"]:
                entry_tier, otm_dist = "WideCondor", otm_w

        # 11. Bear-Call
        if (not entry_tier
                and (week + ("_mon" if dow==0 else "_wed" if dow==2 else "_fri")) not in used_layers
                and bear_bias
                and score <= 2
                and atr <= 200
                and vix < vix_ceiling
                and dual_ok):
            adj = float(adaptive_otm(OTM_DIST_BASE["Bear-Call"], atr))
            s   = compute_safety(row, adj)
            if s >= SAFETY_FLOOR["Bear-Call"]:
                entry_tier, otm_dist = "Bear-Call", adj

        # 12. Core spreads (Aggressive / Normal / Cautious)
        if not entry_tier and (week + ("_mon" if dow==0 else "_wed" if dow==2 else "_fri")) not in used_layers and not v19_velocity_blocked:
            if score == 0 and atr < 150 and vix < 12 and vix_stb and dual_ok and atr < HIGH_ATR_MIN:
                adj = float(adaptive_otm(OTM_DIST_BASE["Aggressive"], atr))
                s   = compute_safety(row, adj)
                if s >= SAFETY_FLOOR["Aggressive"]:
                    entry_tier, otm_dist = "Aggressive", adj
            elif score < 3 and atr <= 180 and vix < vix_ceiling and vix_stb and dual_ok and atr < HIGH_ATR_MIN:
                adj = float(adaptive_otm(OTM_DIST_BASE["Normal"], atr))
                s   = compute_safety(row, adj)
                if s >= SAFETY_FLOOR["Normal"]:
                    entry_tier, otm_dist = "Normal", adj
            elif score < 3 and atr <= 250 and atr < HIGH_ATR_MIN:
                adj = float(adaptive_otm(OTM_DIST_BASE["Cautious"], atr))
                s   = compute_safety(row, adj)
                if s >= SAFETY_FLOOR["Cautious"]:
                    entry_tier, otm_dist = "Cautious", adj

        # 13. V15-A: High-ATR Cautious (fires when normal tiers blocked by ATR)
        if (not entry_tier
                and HIGH_ATR_MIN <= atr <= HIGH_ATR_MAX
                and vix < 20
                and score < 3):
            s = compute_safety(row, 750.0)
            if s >= SAFETY_FLOOR["HighATR-Cautious"]:
                entry_tier, otm_dist = "HighATR-Cautious", 750.0

        if not entry_tier:
            continue

        # ── Determine hold days ──────────────────────────────────────────────
        if entry_tier == "Thursday-EXP":
            hd = HOLD_DAYS_THURS
        elif entry_tier == "Friday-SNP":
            hd = HOLD_DAYS_FRI
        elif entry_tier == "Butterfly":
            hd = HOLD_DAYS_BUTTERFLY
        else:
            hd = HOLD_DAYS

        hold_slice = df.iloc[i + 1: i + hd + 1]
        if len(hold_slice) < 1:
            continue

        safety = compute_safety(row, otm_dist, hd)

        # ── Weekly heat cap ──────────────────────────────────────────────────
        base_tier = entry_tier.replace("NarrowCondor", "NarrowCondor-BP").replace("WideCondor", "WideCondor-BP")
        risk_this = SPREAD_WIDTH - PREMIUM_BASE.get(base_tier, PREMIUM_BASE.get("Normal", 60))
        if entry_tier in ("CONDOR", "NarrowCondor", "WideCondor", "Butterfly"):
            risk_this *= 2
        if weekly_heat + risk_this > weekly_cap:
            continue

        size = lot_size(safety, entry_tier)

        # ── Execute trade ────────────────────────────────────────────────────
        is_condor_type = entry_tier in ("CONDOR", "NarrowCondor", "WideCondor")
        is_butterfly   = entry_tier == "Butterfly"
        is_bear_call   = entry_tier == "Bear-Call"

        if is_condor_type:
            bp_tier = {"CONDOR": "Condor-BP", "NarrowCondor": "NarrowCondor-BP", "WideCondor": "WideCondor-BP"}[entry_tier]
            bc_tier = {"CONDOR": "Condor-BC", "NarrowCondor": "NarrowCondor-BC", "WideCondor": "WideCondor-BC"}[entry_tier]
            if entry_tier == "CONDOR":
                put_leg  = float(adaptive_otm(float(450 if roc1 > 0.3 else 500), atr))
                call_leg = float(adaptive_otm(float(450 if roc1 < -0.3 else 500), atr))
            else:
                put_leg = call_leg = otm_dist

            pnl_bp, d_bp = simulate_trade(hold_slice, row["close"], bp_tier, put_leg,  False, hd)
            pnl_bc, d_bc = simulate_trade(hold_slice, row["close"], bc_tier, call_leg, True,  hd)
            total_pnl = pnl_bp + pnl_bc
            day_exit  = max(d_bp, d_bc)
            result    = "WIN" if total_pnl > 0 else "LOSS"
            prem_total= PREMIUM_BASE.get(bp_tier, 80) + PREMIUM_BASE.get(bc_tier, 80)
            trades.append({
                "Date": curr_date, "Tier": entry_tier,
                "OTM": f"{int(put_leg)}+{int(call_leg)}",
                "ShortOTM": int(put_leg), "LongOTM": int(put_leg) + int(SPREAD_WIDTH),
                "Safety": round(safety, 1), "Premium": prem_total,
                "PnL": round(total_pnl, 1), "DaysHeld": day_exit,
                "Result": result, "Risk": round(risk_this, 1),
                "Side": "Condor",
                "VIX": round(vix, 2), "ATR": round(atr, 1),
                "Score": score, "Size": size, "Week": week,
                "WeekCap": weekly_cap, "Year": curr_date.year,
                "Regime": regime,
            })
            used_condor.add(week)

        elif is_butterfly:
            # Both wings
            pnl_put,  d_put  = simulate_trade(hold_slice, row["close"], "Butterfly", otm_dist, False, hd)
            pnl_call, d_call = simulate_trade(hold_slice, row["close"], "Butterfly", otm_dist, True,  hd)
            total_pnl = pnl_put + pnl_call
            day_exit  = max(d_put, d_call)
            result    = "WIN" if total_pnl > 0 else "LOSS"
            trades.append({
                "Date": curr_date, "Tier": "Butterfly",
                "OTM": f"±{int(otm_dist)}",
                "ShortOTM": int(otm_dist), "LongOTM": int(otm_dist) + int(BUTTERFLY_WIDTH),
                "Safety": round(safety, 1), "Premium": PREMIUM_BASE["Butterfly"],
                "PnL": round(total_pnl, 1), "DaysHeld": day_exit,
                "Result": result, "Risk": round(risk_this, 1),
                "Side": "Butterfly",
                "VIX": round(vix, 2), "ATR": round(atr, 1),
                "Score": score, "Size": size, "Week": week,
                "WeekCap": weekly_cap, "Year": curr_date.year,
                "Regime": regime,
            })
            used_butterfly.add(week)

        else:
            pnl, day_exit = simulate_trade(hold_slice, row["close"], entry_tier, otm_dist, is_bear_call, hd)
            result = "WIN" if pnl > 0 else "LOSS"
            spread_otm = int(otm_dist)
            trades.append({
                "Date": curr_date, "Tier": entry_tier,
                "OTM": str(spread_otm),
                "ShortOTM": spread_otm, "LongOTM": spread_otm + int(SPREAD_WIDTH),
                "Safety": round(safety, 1), "Premium": PREMIUM_BASE.get(entry_tier, 60),
                "PnL": round(pnl, 1), "DaysHeld": day_exit,
                "Result": result, "Risk": round(risk_this, 1),
                "Side": "Bear Call" if is_bear_call else "Bull Put",
                "VIX": round(vix, 2), "ATR": round(atr, 1),
                "Score": score, "Size": size, "Week": week,
                "WeekCap": weekly_cap, "Year": curr_date.year,
                "Regime": regime,
            })
        if entry_tier in ("Aggressive", "Normal", "Cautious", "Bear-Call", "Monday-RW", "Wednesday-MW", "Friday-SNP"):
            used_layers.add(week + ("_mon" if dow==0 else "_wed" if dow==2 else "_fri"))
        elif entry_tier == "Tuesday-LV":
            used_tuesday.add(week)
        elif entry_tier == "Thursday-EXP":
            used_thursday.add(week)

        # ── V15-C: Circuit breaker — 1 loss = 72hr pause ────────────────────
        if result == "LOSS":
            circuit_breaker_until = curr_date + timedelta(days=3)
            consecutive_losses    = 0   # reset — already pausing
        else:
            consecutive_losses = 0

    return pd.DataFrame(trades)


# ─────────────────────────────────────────────────────────────────────────────
# REPORT
# ─────────────────────────────────────────────────────────────────────────────

def print_report(results: pd.DataFrame, compare_path: str = None) -> None:
    if results.empty:
        print("No trades generated. Check data files.")
        return

    total  = len(results)
    wins   = (results["Result"] == "WIN").sum()
    wr     = wins / total * 100
    pnl    = results["PnL"].sum()
    months = (results["Date"].max() - results["Date"].min()).days / 30.44
    max_dd = _max_drawdown(results)

    print("\n" + "═" * 68)
    print("  NIFTY SpreadGuard V16 — Dynamic OTM Engine — Backtest Report")
    print("═" * 68)
    print(f"  Period          : {results['Date'].min().date()} → {results['Date'].max().date()}")
    print(f"  Months          : {months:.1f}")
    print(f"  Total Trades    : {total}")
    print(f"  Trades / Month  : {total / months:.1f}  ← target 5–8")
    print(f"  Win Rate        : {wr:.1f}%  ← target 96%+")
    print(f"  Total PnL       : {pnl:.0f} pts")
    print(f"  Monthly PnL     : {pnl / months:.0f} pts/month")
    print(f"  Institutional ₹ : ₹{pnl * QTY_PER_LOT:,.0f} (Total for {QTY_PER_LOT} Qty)")
    print(f"  Monthly ₹       : ₹{pnl / months * QTY_PER_LOT:,.0f} (per Month)")
    print(f"  Max Drawdown    : {max_dd:.0f} pts (₹{max_dd * QTY_PER_LOT:,.0f})")
    print("─" * 68)

    # Per-tier breakdown
    print(f"\n  {'Tier':<20} {'Trades':>6} {'WR%':>7} {'Avg PnL':>9} {'Total':>9}")
    print("  " + "─" * 56)
    for tier, grp in results.groupby("Tier"):
        tw   = (grp["Result"] == "WIN").sum()
        wr_t = tw / len(grp) * 100
        print(f"  {tier:<20} {len(grp):>6} {wr_t:>6.1f}% "
              f"{grp['PnL'].mean():>8.1f} {grp['PnL'].sum():>9.0f}")

    print("─" * 68)

    # Per-year breakdown
    print(f"\n  {'Year':<6} {'Trades':>6} {'WR%':>7} {'PnL':>9} {'₹/mo(2L)':>12}")
    print("  " + "─" * 44)
    for yr, grp in results.groupby("Year"):
        tw   = (grp["Result"] == "WIN").sum()
        wr_t = tw / len(grp) * 100
        mo   = 12
        inr  = grp["PnL"].sum() / mo * QTY_PER_LOT
        print(f"  {yr:<6} {len(grp):>6} {wr_t:>6.1f}% {grp['PnL'].sum():>9.0f} {inr:>11,.0f}")

    print("─" * 68)

    # Regime breakdown
    if "Regime" in results.columns:
        print(f"\n  {'Regime':<14} {'Trades':>6} {'WR%':>7} {'PnL':>9}")
        print("  " + "─" * 40)
        for reg, grp in results.groupby("Regime"):
            tw   = (grp["Result"] == "WIN").sum()
            wr_t = tw / len(grp) * 100
            print(f"  {reg:<14} {len(grp):>6} {wr_t:>6.1f}% {grp['PnL'].sum():>9.0f}")

    # Side breakdown
    if "Side" in results.columns:
        print(f"\n  {'Side':<14} {'Trades':>6} {'WR%':>7} {'Avg PnL':>9}")
        print("  " + "─" * 40)
        for side, grp in results.groupby("Side"):
            tw   = (grp["Result"] == "WIN").sum()
            wr_t = tw / len(grp) * 100
            print(f"  {side:<14} {len(grp):>6} {wr_t:>6.1f}% {grp['PnL'].mean():>9.1f}")

    print("\n  V16 New Tiers:")
    for t in ["Butterfly", "NarrowCondor", "WideCondor"]:
        grp = results[results["Tier"] == t]
        if not grp.empty:
            tw   = (grp["Result"] == "WIN").sum()
            wr_t = tw / len(grp) * 100
            print(f"    {t:<20}: {len(grp)} trades | {wr_t:.1f}% WR | "
                  f"{grp['PnL'].sum():.0f} pts total")
        else:
            print(f"    {t:<20}: 0 trades (conditions never met in date range)")

    if compare_path:
        _compare(results, compare_path)

    print("═" * 68)


def _max_drawdown(results: pd.DataFrame) -> float:
    equity = results["PnL"].cumsum()
    roll_max = equity.cummax()
    drawdown = roll_max - equity
    return float(drawdown.max())


def _compare(v16: pd.DataFrame, path: str) -> None:
    try:
        other = pd.read_csv(path, parse_dates=["Date"])
    except Exception:
        return
    other_name = path.replace("backtest_", "").replace("_results.csv", "").upper()
    print(f"\n  Comparison: V16 vs {other_name}")
    print(f"  {'Metric':<22} {'V16':>12} {other_name:>12}")
    print("  " + "─" * 48)

    for label, v16_val, other_val in [
        ("Total trades", len(v16), len(other)),
        ("Win rate %", f"{(v16['Result']=='WIN').sum()/len(v16)*100:.1f}",
                       f"{(other['Result']=='WIN').sum()/len(other)*100:.1f}"),
        ("Total PnL pts", f"{v16['PnL'].sum():.0f}", f"{other['PnL'].sum():.0f}"),
        ("Max DD pts",    f"{_max_drawdown(v16):.0f}", f"{_max_drawdown(other):.0f}"),
    ]:
        print(f"  {label:<22} {str(v16_val):>12} {str(other_val):>12}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SpreadGuard V16 Backtest Engine")
    parser.add_argument("--start",   default=None,  help="Start date YYYY-MM-DD")
    parser.add_argument("--end",     default=None,  help="End date YYYY-MM-DD")
    parser.add_argument("--year",    default=None,  help="Single year, e.g. 2024")
    parser.add_argument("--compare", default=None,  help="Path to compare CSV (e.g. backtest_v15_results.csv)")
    parser.add_argument("--nifty",   default="data/nifty_daily.csv")
    parser.add_argument("--vix",     default="data/vix_daily.csv")
    args = parser.parse_args()

    if args.year:
        args.start = f"{args.year}-01-01"
        args.end   = f"{args.year}-12-31"

    print("SpreadGuard V16 — Dynamic OTM Engine")
    print("Loading data...")
    nifty, vix = load_data(args.nifty, args.vix)
    if nifty is None:
        return

    print("Computing indicators...")
    df = compute_flags(nifty, vix)

    print(f"Running V16 backtest"
          + (f"  [{args.start} → {args.end}]" if args.start else "") + "...")
    results = run_v2024_backtest(df, args.start, args.end)

    print_report(results, args.compare)

    out = "backtest_v2024_results.csv"
    results.to_csv(out, index=False)
    print(f"\n  Saved → {out}")


if __name__ == "__main__":
    main()
