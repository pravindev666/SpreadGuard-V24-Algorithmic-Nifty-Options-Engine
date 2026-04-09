"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   SpreadGuard V2024 — HighATR Permutation Scanner                          ║
║   Tests all combinations of HIGH_ATR_MAX (240→500) x OTM (150→750)        ║
║   Ranks by composite score: Win Rate + Monthly PnL - Max Drawdown          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Usage:
    python permutation_scanner.py
    python permutation_scanner.py --start 2020-01-01 --end 2024-12-31
    python permutation_scanner.py --top 20
    python permutation_scanner.py --nifty data/nifty_daily.csv --vix data/vix_daily.csv
"""

import argparse
import warnings
import itertools
from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.stats import norm

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# PERMUTATION GRID — edit these to expand/shrink the search space
# ─────────────────────────────────────────────────────────────────────────────

ATR_MAX_GRID = [240, 260, 280, 300, 320, 350, 380, 400, 450, 500]
OTM_GRID     = [150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750]

# ─────────────────────────────────────────────────────────────────────────────
# BASE CONFIG (V2024 — unchanged)
# ─────────────────────────────────────────────────────────────────────────────

QTY_PER_LOT = 65  # Institutional Standard

SLIPPAGE = {
    "Aggressive": -5, "Normal": -5, "Cautious": -8, "Bear-Call": -10,
    "Tuesday-LV": -5, "Wednesday-MW": -7, "Monday-RW": -7, "Friday-SNP": -8,
    "VIX-Collapse": -8, "Near-VC": -8, "Condor-BP": -5, "Condor-BC": -10,
    "Thursday-EXP": -5, "HighATR-Cautious": -8,
    "Butterfly": -12, "NarrowCondor-BP": -8, "NarrowCondor-BC": -8,
    "WideCondor-BP": -5, "WideCondor-BC": -5,
}
PREMIUM_BASE = {
    "Aggressive": 100, "Normal": 60, "Cautious": 40, "Bear-Call": 60,
    "Tuesday-LV": 40, "Wednesday-MW": 50, "Monday-RW": 45, "Friday-SNP": 42,
    "VIX-Collapse": 100, "Near-VC": 80, "Condor-BP": 80, "Condor-BC": 80,
    "Thursday-EXP": 35, "HighATR-Cautious": 30,
    "Butterfly": 180, "NarrowCondor-BP": 110, "NarrowCondor-BC": 110,
    "WideCondor-BP": 50, "WideCondor-BC": 50,
}
TP_MULTIPLIER = {
    "DEFAULT": 0.35, "Aggressive": 0.70, "Normal": 0.60, "Cautious": 0.60,
    "Bear-Call": 0.70, "Tuesday-LV": 0.65, "Wednesday-MW": 0.62,
    "Monday-RW": 0.62, "Friday-SNP": 0.58, "VIX-Collapse": 0.70,
    "Near-VC": 0.65, "Condor-BP": 0.60, "Condor-BC": 0.60,
    "Thursday-EXP": 0.50, "HighATR-Cautious": 0.55,
    "Butterfly": 0.50, "NarrowCondor-BP": 0.60, "NarrowCondor-BC": 0.60,
    "WideCondor-BP": 0.62, "WideCondor-BC": 0.62,
}
SAFETY_FLOOR = {
    "Aggressive": 75.0, "Normal": 75.0, "Cautious": 72.0, "Bear-Call": 75.0,
    "Tuesday-LV": 70.0, "Wednesday-MW": 73.0, "Monday-RW": 73.0,
    "Friday-SNP": 90.0, "VIX-Collapse": 65.0, "Near-VC": 68.0,
    "Condor-BP": 75.0, "Condor-BC": 75.0, "Thursday-EXP": 85.0,
    "HighATR-Cautious": 78.0, "Butterfly": 80.0,
    "NarrowCondor-BP": 80.0, "NarrowCondor-BC": 80.0,
    "WideCondor-BP": 75.0, "WideCondor-BC": 75.0,
}

HOLD_DAYS             = 7
HOLD_DAYS_THURS       = 1
HOLD_DAYS_FRI         = 6
HOLD_DAYS_BUTTERFLY   = 5
SPREAD_WIDTH          = 200.0
BUTTERFLY_WIDTH       = 300.0
CONDOR_VIX_MIN        = 12.0
CONDOR_VIX_MAX        = 20.0
CONDOR_ATR_MIN        = 120.0
CONDOR_ATR_MAX        = 180.0
VIX_SPIKE_SUPPRESS    = 4.0
ATR_NORM_REF          = 150.0
ADAPTIVE_OTM_MIN      = 0.90
ADAPTIVE_OTM_MAX      = 1.10
HIGH_ATR_MIN          = 180.0
BUTTERFLY_ATR_MAX     = 130.0
BUTTERFLY_VIX_MAX     = 12.0
NARROW_CONDOR_ATR_MAX = 140.0
NARROW_CONDOR_VIX_MAX = 16.0
WIDE_CONDOR_ATR_MIN   = 160.0
WIDE_CONDOR_ATR_MAX   = 200.0
WEEKLY_RISK_LIMIT     = 600.0
WEEKLY_RISK_LIMIT_NORMAL = 420.0
WEEKLY_RISK_LIMIT_ELEV   = 300.0
WEEKLY_RISK_LIMIT_HIGH   = 200.0
VIX_BAND_NORMAL_MULT  = 1.20
VIX_BAND_NORMAL_CAP   = 22.0
VELOCITY_THRESHOLD    = 4.5

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def vix_bands(v20):
    avg = v20 if not np.isnan(v20) else 15.0
    return min(avg * VIX_BAND_NORMAL_MULT, VIX_BAND_NORMAL_CAP)

def norm_cdf(x):
    return float(norm.cdf(x))

def compute_safety(row, otm_dist, hold_days=7):
    c, atr = row["close"], row["atr"]
    if c <= 0 or atr <= 0:
        return 0.0
    z = (otm_dist / c) / ((atr / c) * np.sqrt(hold_days))
    return (1.0 - (1.0 - norm_cdf(z)) * 2.0) * 100.0

def adaptive_otm(base_otm, atr):
    ratio = max(ADAPTIVE_OTM_MIN, min(ADAPTIVE_OTM_MAX, atr / ATR_NORM_REF))
    return int(round(base_otm * ratio / 50) * 50)

def weekly_heat_cap(vix, atr, score):
    if atr > HIGH_ATR_MIN:
        return WEEKLY_RISK_LIMIT_HIGH
    if atr > 150 or vix > 16:
        return WEEKLY_RISK_LIMIT_ELEV
    if vix < 12 and score == 0:
        return WEEKLY_RISK_LIMIT
    return WEEKLY_RISK_LIMIT_NORMAL

def lot_size(safety, tier):
    fixed_75 = {"Near-VC", "Thursday-EXP", "Wednesday-MW", "Monday-RW",
                "Friday-SNP", "HighATR-Cautious", "Butterfly",
                "NarrowCondor-BP", "WideCondor-BP"}
    if tier in fixed_75:
        return 0.75
    return 1.5 if safety > 95 else 1.0 if safety > 85 else 0.75

def simulate_trade(hold_slice, entry_close, tier, otm_dist, is_bear_call, hold_days):
    premium = PREMIUM_BASE.get(tier, 60)
    tp_pts  = premium * TP_MULTIPLIER.get(tier, 0.60)
    slip    = SLIPPAGE.get(tier, -5)
    sw      = BUTTERFLY_WIDTH if "Butterfly" in tier else SPREAD_WIDTH
    short_strike = entry_close + otm_dist if is_bear_call else entry_close - otm_dist
    entry_net    = premium + slip

    for day_idx, (_, bar) in enumerate(hold_slice.iterrows(), start=1):
        price     = bar["close"]
        remaining = max(0, short_strike - price) if is_bear_call else max(0, price - short_strike)
        decay_pct = 1.0 - remaining / premium if premium > 0 else 1.0
        if decay_pct >= TP_MULTIPLIER.get(tier, 0.60):
            return round(tp_pts + slip, 1), day_idx
        if day_idx == 3:
            if is_bear_call and price > entry_close + otm_dist * 0.5:
                return round(entry_net * 0.85, 1), day_idx
            if not is_bear_call and price < entry_close - otm_dist * 0.5:
                return round(entry_net * 0.85, 1), day_idx
        if is_bear_call and price >= short_strike:
            return round(-(sw - premium) + slip, 1), day_idx
        if not is_bear_call and price <= short_strike:
            return round(-(sw - premium) + slip, 1), day_idx
    return round(tp_pts + slip, 1), len(hold_slice)

# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────

def load_data(nifty_path, vix_path):
    try:
        nifty = pd.read_csv(nifty_path, parse_dates=["date"])
        vix   = pd.read_csv(vix_path,   parse_dates=["date"])
    except FileNotFoundError as e:
        print(f"Data file not found: {e}")
        return None, None
    nifty.columns = nifty.columns.str.lower().str.strip()
    vix.columns   = vix.columns.str.lower().str.strip()
    return (nifty.sort_values("date").reset_index(drop=True),
            vix.sort_values("date").reset_index(drop=True))

def compute_flags(nifty, vix):
    df = pd.merge(nifty, vix[["date", "close"]], on="date", how="inner",
                  suffixes=("", "_vix"))
    df["prev_close"]      = df["close"].shift(1)
    df["prev_close_vix"]  = df["close_vix"].shift(1)
    df["vix_chg_1d"]      = (df["close_vix"] - df["prev_close_vix"]) / df["prev_close_vix"] * 100
    df["vix_2d_chg"]      = df["close_vix"].pct_change(2) * 100
    df["vix_5d_std"]      = df["close_vix"].rolling(5).std()
    df["tr"] = np.maximum(
        (df["high"] - df["low"]).abs(),
        np.maximum((df["high"] - df["prev_close"]).abs(),
                   (df["low"]  - df["prev_close"]).abs()))
    df["atr"]        = df["tr"].ewm(alpha=1/14, adjust=False).mean()
    df["ema20"]      = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"]      = df["close"].ewm(span=50, adjust=False).mean()
    df["vix_20d_avg"]= df["close_vix"].rolling(20).mean()
    df["roc5"]       = df["close"].pct_change(5) * 100
    df["roc1"]       = df["close"].pct_change(1) * 100
    df["velocity"]   = df["roc1"].abs() + df["roc1"].shift(1).abs() + df["roc1"].shift(2).abs()
    df["bb_mid"]     = df["close"].rolling(20).mean()
    df["bb_std"]     = df["close"].rolling(20).std()
    df["bbw"]        = (4 * df["bb_std"]) / df["bb_mid"] * 100
    df["bbw_avg"]    = df["bbw"].rolling(20).mean()
    df["avg_gap"]    = (df["close"] - df["prev_close"]).abs() / df["prev_close"] * 100
    df["avg_gap_10"] = df["avg_gap"].rolling(10).mean()
    df["open_gap_pct"]= (df["open"] - df["prev_close"]).abs() / df["prev_close"] * 100
    df["day_of_week"] = df["date"].dt.dayofweek
    df["score"] = (
        (df["close_vix"] > 20).astype(int) +
        (df["vix_chg_1d"] > 15).astype(int) +
        (df["atr"] > 220).astype(int) +
        (df["roc5"].abs() > 2.5).astype(int) +
        (df["bbw"] > df["bbw_avg"] * 1.3).astype(int) +
        (df["avg_gap_10"] > 0.8).astype(int)
    ).clip(0, 6)
    df["week_key"] = (df["date"].dt.isocalendar().year.astype(str) + "_" +
                      df["date"].dt.isocalendar().week.astype(str).str.zfill(2))
    df["regime"] = np.where(df["close_vix"] < 12, "ultra-calm",
                   np.where(df["close_vix"] < 16, "normal",
                   np.where(df["close_vix"] < 20, "elevated",
                   np.where(df["close_vix"] < 25, "high", "crisis"))))
    return df.dropna(subset=["atr", "ema20"]).reset_index(drop=True)

# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest(df, start_date=None, end_date=None,
                 high_atr_max=240, high_atr_otm=750.0):
    if start_date:
        df = df[df["date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["date"] <= pd.Timestamp(end_date)]
    df = df.reset_index(drop=True)

    trades               = []
    used_layers          = set()
    used_thursday        = set()
    used_condor          = set()
    used_butterfly       = set()
    circuit_breaker_until= pd.Timestamp("2000-01-01")

    for i, row in df.iterrows():
        if i + 1 >= len(df):
            break
        curr_date = row["date"]
        if curr_date <= circuit_breaker_until:
            continue

        vix     = row["close_vix"]
        atr     = row["atr"]
        score   = int(row["score"])
        vix_chg = row["vix_chg_1d"]
        roc1    = row["roc1"]
        week    = row["week_key"]
        dow     = row["day_of_week"]

        velocity    = row.get("velocity", 0.0)
        vix_ceiling = vix_bands(row.get("vix_20d_avg", 15.0))
        v_blocked   = (velocity > VELOCITY_THRESHOLD and score >= 1)

        if vix >= 26 or vix_chg > VIX_SPIKE_SUPPRESS or row["open_gap_pct"] > 0.8:
            continue

        vix_5d_std = row["vix_5d_std"] if not np.isnan(row["vix_5d_std"]) else 99
        vix_stb    = vix_5d_std < 1.5
        bull_bias  = (row["ema20"] > row["ema50"]) and (row["close"] > row["ema50"]) and (row["roc5"] > 0.5)
        bear_bias  = (row["ema20"] < row["ema50"]) and (row["close"] < row["ema50"]) and (row["roc5"] < -0.5)
        neut_bias  = not bull_bias and not bear_bias
        dual_ok    = (vix < vix_ceiling) and (atr < 200)
        ultra_calm = (score == 0) and (vix < 12) and (atr < 150) and vix_stb
        weekly_cap = weekly_heat_cap(vix, atr, score)
        weekly_heat= sum(t.get("Risk", 0) for t in trades if t.get("Week") == week)

        entry_tier = None
        otm_dist   = 0.0

        # 1. VIX-Collapse
        if row["vix_2d_chg"] < -15 and score < 3 and vix < vix_ceiling and atr < 250:
            if compute_safety(row, 700.0) >= SAFETY_FLOOR["VIX-Collapse"]:
                entry_tier, otm_dist = "VIX-Collapse", 700.0

        # 2. Near-VIX-Collapse
        if not entry_tier and -15 <= row["vix_2d_chg"] < -10 and score < 3 and vix < vix_ceiling:
            if compute_safety(row, 700.0) >= SAFETY_FLOOR["Near-VC"]:
                entry_tier, otm_dist = "Near-VC", 700.0

        # 3. Butterfly
        if (not entry_tier and week not in used_butterfly and ultra_calm
                and atr <= BUTTERFLY_ATR_MAX and vix <= BUTTERFLY_VIX_MAX and score == 0):
            if compute_safety(row, 200.0, HOLD_DAYS_BUTTERFLY) >= SAFETY_FLOOR["Butterfly"]:
                entry_tier, otm_dist = "Butterfly", 200.0

        # 4. Thursday Expiry
        if (not entry_tier and week not in used_thursday and dow == 3
                and score <= 1 and vix < 14 and atr < 100 and vix < vix_ceiling):
            adj = adaptive_otm(600, atr)
            if compute_safety(row, adj, HOLD_DAYS_THURS) >= SAFETY_FLOOR["Thursday-EXP"]:
                entry_tier, otm_dist = "Thursday-EXP", float(adj)

        # 5. Friday Sniper
        if (not entry_tier and (week + "_fri") not in used_layers
                and dow == 4 and score <= 1 and vix <= 14 and atr <= 130 and dual_ok):
            adj = adaptive_otm(640, atr)
            if compute_safety(row, adj, HOLD_DAYS_FRI) >= SAFETY_FLOOR["Friday-SNP"]:
                entry_tier, otm_dist = "Friday-SNP", float(adj)

        # 6. Monday Recovery
        if (not entry_tier and (week + "_mon") not in used_layers and not v_blocked
                and dow == 0 and score <= 1 and vix < 16 and atr <= 160 and dual_ok):
            adj = adaptive_otm(680, atr)
            if compute_safety(row, adj) >= SAFETY_FLOOR["Monday-RW"]:
                entry_tier, otm_dist = "Monday-RW", float(adj)

        # 7. Wednesday Midweek
        if (not entry_tier and (week + "_wed") not in used_layers and not v_blocked
                and dow == 2 and score <= 1 and vix < vix_ceiling and atr <= 180):
            adj = adaptive_otm(650, atr)
            if compute_safety(row, adj) >= SAFETY_FLOOR["Wednesday-MW"]:
                entry_tier, otm_dist = "Wednesday-MW", float(adj)

        # 8. Narrow Condor
        if (not entry_tier and week not in used_condor and neut_bias and score <= 1
                and atr <= NARROW_CONDOR_ATR_MAX and vix <= NARROW_CONDOR_VIX_MAX and vix_stb):
            if compute_safety(row, 400.0) >= SAFETY_FLOOR["NarrowCondor-BP"]:
                entry_tier, otm_dist = "NarrowCondor", 400.0

        # 9. Iron Condor
        if (not entry_tier and (week + "_wed") not in used_layers and neut_bias
                and score <= 2 and CONDOR_VIX_MIN <= vix <= CONDOR_VIX_MAX
                and CONDOR_ATR_MIN <= atr <= CONDOR_ATR_MAX and vix_stb and dual_ok):
            pl = float(adaptive_otm(500, atr))
            if (compute_safety(row, pl) >= SAFETY_FLOOR["Condor-BP"] and
                compute_safety(row, pl) >= SAFETY_FLOOR["Condor-BC"]):
                entry_tier, otm_dist = "CONDOR", pl

        # 10. Wide Condor
        if (not entry_tier and (week + "_wed") not in used_layers and neut_bias
                and score <= 2 and WIDE_CONDOR_ATR_MIN <= atr <= WIDE_CONDOR_ATR_MAX
                and vix < 20 and vix_stb):
            if compute_safety(row, 600.0) >= SAFETY_FLOOR["WideCondor-BP"]:
                entry_tier, otm_dist = "WideCondor", 600.0

        # 11. Bear-Call
        if (not entry_tier and bear_bias and score <= 2 and atr <= 200
                and vix < vix_ceiling and dual_ok):
            adj = float(adaptive_otm(600, atr))
            if compute_safety(row, adj) >= SAFETY_FLOOR["Bear-Call"]:
                entry_tier, otm_dist = "Bear-Call", adj

        # 12. Core spreads
        if not entry_tier and not v_blocked:
            if score == 0 and atr < 150 and vix < 12 and vix_stb and dual_ok:
                adj = float(adaptive_otm(500, atr))
                if compute_safety(row, adj) >= SAFETY_FLOOR["Aggressive"]:
                    entry_tier, otm_dist = "Aggressive", adj
            elif score < 3 and atr <= 180 and vix < vix_ceiling and vix_stb and dual_ok:
                adj = float(adaptive_otm(600, atr))
                if compute_safety(row, adj) >= SAFETY_FLOOR["Normal"]:
                    entry_tier, otm_dist = "Normal", adj
            elif score < 3 and atr <= 250:
                adj = float(adaptive_otm(700, atr))
                if compute_safety(row, adj) >= SAFETY_FLOOR["Cautious"]:
                    entry_tier, otm_dist = "Cautious", adj

        # 13. HighATR-Cautious ← PERMUTED PARAMETERS
        if (not entry_tier and HIGH_ATR_MIN <= atr <= high_atr_max
                and vix < 20 and score < 3):
            if compute_safety(row, float(high_atr_otm)) >= SAFETY_FLOOR["HighATR-Cautious"]:
                entry_tier, otm_dist = "HighATR-Cautious", float(high_atr_otm)

        if not entry_tier:
            continue

        hd = (HOLD_DAYS_THURS if entry_tier == "Thursday-EXP"
              else HOLD_DAYS_FRI if entry_tier == "Friday-SNP"
              else HOLD_DAYS_BUTTERFLY if entry_tier == "Butterfly"
              else HOLD_DAYS)

        hold_slice = df.iloc[i + 1: i + hd + 1]
        if len(hold_slice) < 1:
            continue

        safety    = compute_safety(row, otm_dist, hd)
        base_tier = entry_tier.replace("NarrowCondor", "NarrowCondor-BP").replace("WideCondor", "WideCondor-BP")
        risk_this = SPREAD_WIDTH - PREMIUM_BASE.get(base_tier, PREMIUM_BASE.get("Normal", 60))
        if entry_tier in ("CONDOR", "NarrowCondor", "WideCondor", "Butterfly"):
            risk_this *= 2
        if weekly_heat + risk_this > weekly_cap:
            continue

        is_condor  = entry_tier in ("CONDOR", "NarrowCondor", "WideCondor")
        is_bfly    = entry_tier == "Butterfly"
        is_bc      = entry_tier == "Bear-Call"

        if is_condor:
            bp_t = {"CONDOR": "Condor-BP", "NarrowCondor": "NarrowCondor-BP", "WideCondor": "WideCondor-BP"}[entry_tier]
            bc_t = {"CONDOR": "Condor-BC", "NarrowCondor": "NarrowCondor-BC", "WideCondor": "WideCondor-BC"}[entry_tier]
            pnl_bp, d_bp = simulate_trade(hold_slice, row["close"], bp_t, otm_dist, False, hd)
            pnl_bc, d_bc = simulate_trade(hold_slice, row["close"], bc_t, otm_dist, True,  hd)
            total_pnl = pnl_bp + pnl_bc
            result    = "WIN" if total_pnl > 0 else "LOSS"
            trades.append({"Date": curr_date, "Tier": entry_tier,
                "PnL": round(total_pnl, 1), "Result": result, "Risk": round(risk_this, 1),
                "VIX": round(vix, 2), "ATR": round(atr, 1), "Week": week, "Year": curr_date.year})
            used_condor.add(week)
        elif is_bfly:
            p1, _ = simulate_trade(hold_slice, row["close"], "Butterfly", otm_dist, False, hd)
            p2, _ = simulate_trade(hold_slice, row["close"], "Butterfly", otm_dist, True,  hd)
            total_pnl = p1 + p2
            result    = "WIN" if total_pnl > 0 else "LOSS"
            trades.append({"Date": curr_date, "Tier": "Butterfly",
                "PnL": round(total_pnl, 1), "Result": result, "Risk": round(risk_this, 1),
                "VIX": round(vix, 2), "ATR": round(atr, 1), "Week": week, "Year": curr_date.year})
            used_butterfly.add(week)
        else:
            pnl, _ = simulate_trade(hold_slice, row["close"], entry_tier, otm_dist, is_bc, hd)
            result  = "WIN" if pnl > 0 else "LOSS"
            trades.append({"Date": curr_date, "Tier": entry_tier,
                "PnL": round(pnl, 1), "Result": result, "Risk": round(risk_this, 1),
                "VIX": round(vix, 2), "ATR": round(atr, 1), "Week": week, "Year": curr_date.year})

        if entry_tier in ("Aggressive", "Normal", "Cautious", "Bear-Call",
                          "Monday-RW", "Wednesday-MW", "Friday-SNP"):
            used_layers.add(week + ("_mon" if dow==0 else "_wed" if dow==2 else "_fri"))
        elif entry_tier == "Thursday-EXP":
            used_thursday.add(week)

        if result == "LOSS":
            circuit_breaker_until = curr_date + timedelta(days=3)

    return pd.DataFrame(trades)

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARISE ONE RUN
# ─────────────────────────────────────────────────────────────────────────────

def summarise(results, high_atr_max, high_atr_otm):
    if results.empty:
        return None
    total  = len(results)
    wins   = (results["Result"] == "WIN").sum()
    wr     = wins / total * 100
    pnl    = results["PnL"].sum()
    months = max((results["Date"].max() - results["Date"].min()).days / 30.44, 1)
    equity = results["PnL"].cumsum()
    max_dd = float((equity.cummax() - equity).max())

    ha       = results[results["Tier"] == "HighATR-Cautious"]
    ha_n     = len(ha)
    ha_wr    = (ha["Result"] == "WIN").sum() / ha_n * 100 if ha_n > 0 else 0.0
    ha_pnl   = ha["PnL"].sum()
    mo_pnl   = pnl / months
    # Composite score: rewards WR and monthly income, penalises drawdown
    score = round(wr * 0.4 + (mo_pnl * QTY_PER_LOT / 1000) * 0.4 - (max_dd * QTY_PER_LOT / 1000) * 0.2, 2)

    return {
        "ATR_MAX":      high_atr_max,
        "OTM":          int(high_atr_otm),
        "Total_Trades": total,
        "Win_Rate":     round(wr, 1),
        "Total_₹":      round(pnl * QTY_PER_LOT, 0),
        "Monthly_₹":    round(mo_pnl * QTY_PER_LOT, 0),
        "Max_DD_₹":     round(max_dd * QTY_PER_LOT, 0),
        "HA_Trades":    ha_n,
        "HA_WinRate":   round(ha_wr, 1),
        "Composite":    score,
    }

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SpreadGuard HighATR Permutation Scanner")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=None)
    parser.add_argument("--top",   default=20, type=int)
    parser.add_argument("--nifty", default="data/nifty_daily.csv")
    parser.add_argument("--vix",   default="data/vix_daily.csv")
    args = parser.parse_args()

    combos = list(itertools.product(ATR_MAX_GRID, OTM_GRID))
    total  = len(combos)
    print(f"\nSpreadGuard — HighATR Permutation Scanner")
    print(f"Grid: {len(ATR_MAX_GRID)} ATR ceilings × {len(OTM_GRID)} OTM distances = {total} combinations\n")

    nifty, vix = load_data(args.nifty, args.vix)
    if nifty is None:
        return
    df = compute_flags(nifty, vix)
    print(f"Data loaded: {len(df)} trading days  "
          f"({df['date'].min().date()} → {df['date'].max().date()})\n")

    rows = []
    for idx, (atr_max, otm) in enumerate(combos, 1):
        print(f"\r  [{idx:>3}/{total}]  ATR_MAX={atr_max:<4}  OTM={otm:<4}   ", end="", flush=True)
        res = run_backtest(df, args.start, args.end,
                           high_atr_max=atr_max, high_atr_otm=float(otm))
        row = summarise(res, atr_max, otm)
        if row:
            rows.append(row)

    print(f"\n\nDone — {len(rows)} valid combinations.\n")

    df_out = pd.DataFrame(rows).sort_values("Composite", ascending=False).reset_index(drop=True)
    df_out.to_csv("permutation_results.csv", index=False)

    # ── Leaderboard ──────────────────────────────────────────────────────────
    W = 100
    print("=" * W)
    print("  PERMUTATION LEADERBOARD")
    print("  Composite = WinRate×0.4 + MonthlyPnL×0.4 − MaxDD×0.2")
    print("=" * W)
    hdr = (f"  {'#':<4} {'ATR_MAX':<9} {'OTM':<6} {'Trades':<8} {'WR%':<7} "
           f"{'Mo.₹':>8} {'MaxDD.₹':>8} {'HA_n':>6} {'HA_WR%':>8} {'Score':>8}")
    print(hdr)
    print("  " + "─" * 84)
    for i, r in df_out.head(args.top).iterrows():
        tag = "  ← BEST" if i == 0 else ""
        print(f"  {i+1:<4} {int(r.ATR_MAX):<9} {int(r.OTM):<6} "
              f"{int(r.Total_Trades):<8} {r.Win_Rate:<7.1f} "
              f"{r['Monthly_₹']:>8.0f} {r['Max_DD_₹']:>8.0f} "
              f"{int(r.HA_Trades):>6} {r.HA_WinRate:>8.1f} "
              f"{r.Composite:>8.1f}{tag}")

    # ── Worst combos ─────────────────────────────────────────────────────────
    print(f"\n  WORST 5 — avoid these:")
    print(f"  {'#':<4} {'ATR_MAX':<9} {'OTM':<6} {'WR%':<7} {'Mo.₹':>8} {'MaxDD.₹':>8} {'Score':>8}")
    print("  " + "─" * 52)
    for i, r in df_out.tail(5).iterrows():
        print(f"  {i+1:<4} {int(r.ATR_MAX):<9} {int(r.OTM):<6} "
              f"{r.Win_Rate:<7.1f} {r['Monthly_₹']:>8.0f} {r['Max_DD_₹']:>8.0f} {r.Composite:>8.1f}")

    # ── Best OTM per ATR ceiling ──────────────────────────────────────────────
    print(f"  {'ATR_MAX':<9} {'Best_OTM':<10} {'WR%':<7} {'Mo.₹':>8} {'MaxDD.₹':>8} {'HA_WR%':>8}")
    print("  " + "─" * 58)
    for atr_max in sorted(ATR_MAX_GRID):
        sub = df_out[df_out["ATR_MAX"] == atr_max]
        if not sub.empty:
            b = sub.iloc[0]
            print(f"  {int(atr_max):<9} {int(b.OTM):<10} {b.Win_Rate:<7.1f} "
                  f"{b['Monthly_₹']:>8.0f} {b['Max_DD_₹']:>8.0f} {b.HA_WinRate:>8.1f}")

    # ── Safe zone filter ─────────────────────────────────────────────────────
    safe = df_out[(df_out["Win_Rate"] >= 90) & (df_out["Max_DD_₹"] < 500 * QTY_PER_LOT)]
    print(f"\n  SAFE ZONE (WR ≥ 90%, MaxDD.₹ < {500 * QTY_PER_LOT}): {len(safe)} combinations")
    if not safe.empty:
        print(f"  {'ATR_MAX':<9} {'OTM':<6} {'WR%':<7} {'Mo.₹':>8} {'MaxDD.₹':>8}")
        print("  " + "─" * 44)
        for _, r in safe.head(10).iterrows():
            print(f"  {int(r.ATR_MAX):<9} {int(r.OTM):<6} "
                  f"{r.Win_Rate:<7.1f} {r['Monthly_₹']:>8.0f} {r['Max_DD_₹']:>8.0f}")

    df_out.to_csv("permutation_results_v2024_65.csv", index=False)
    print(f"\n  Full results saved → permutation_results_v2024_65.csv")
    print("=" * W)


if __name__ == "__main__":
    main()
