"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   STRIKE BREACH AUDIT — "Would the market actually hit my strikes?"        ║
║                                                                              ║
║   This script replays every trade the V2024 backtest selects, then checks   ║
║   the REAL intraday HIGH and LOW during the hold period to see if the       ║
║   short strike would have been touched.                                     ║
║                                                                              ║
║   The backtest only checks CLOSE price for breach. Reality uses HIGH/LOW.   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import warnings
import numpy as np
import pandas as pd
from scipy.stats import norm
from backtest_spreadguard_v2024 import (
    load_data, compute_flags,
    PREMIUM_BASE, OTM_DIST_BASE, SAFETY_FLOOR, ATR_GATE,
    TP_MULTIPLIER, SLIPPAGE, SPREAD_WIDTH, BUTTERFLY_WIDTH,
    HOLD_DAYS, HOLD_DAYS_THURS, HOLD_DAYS_FRI, HOLD_DAYS_BUTTERFLY,
    CONDOR_VIX_MIN, CONDOR_VIX_MAX, CONDOR_ATR_MIN, CONDOR_ATR_MAX,
    VIX_SPIKE_SUPPRESS, ATR_NORM_REF, ADAPTIVE_OTM_MIN, ADAPTIVE_OTM_MAX,
    HIGH_ATR_MIN, HIGH_ATR_MAX,
    BUTTERFLY_ATR_MAX, BUTTERFLY_VIX_MAX,
    NARROW_CONDOR_ATR_MAX, NARROW_CONDOR_VIX_MAX,
    WIDE_CONDOR_ATR_MIN, WIDE_CONDOR_ATR_MAX,
    WEEKLY_RISK_LIMIT, WEEKLY_RISK_LIMIT_NORMAL,
    WEEKLY_RISK_LIMIT_ELEV, WEEKLY_RISK_LIMIT_HIGH,
    VIX_BAND_NORMAL_MULT, VIX_BAND_NORMAL_CAP,
    VELOCITY_THRESHOLD,
    adaptive_otm, compute_safety, vix_bands, weekly_heat_cap, lot_size,
    QTY_PER_LOT,
)
from datetime import timedelta

warnings.filterwarnings("ignore")

def run_breach_audit():
    print("Loading data...")
    nifty, vix = load_data("data/nifty_daily.csv", "data/vix_daily.csv")
    if nifty is None:
        return

    print("Computing indicators...")
    df = compute_flags(nifty, vix)
    df = df.reset_index(drop=True)

    print(f"Data range: {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"Total bars: {len(df)}\n")

    # ── Replay every trade using IDENTICAL logic to the backtest ──────────
    trades = []
    used_layers     = set()
    used_tuesday    = set()
    used_thursday   = set()
    used_condor     = set()
    used_butterfly  = set()
    circuit_breaker_until = pd.Timestamp("2000-01-01")

    for i, row in df.iterrows():
        if i + 1 >= len(df):
            break

        curr_date = row["date"]
        if curr_date <= circuit_breaker_until:
            continue

        vix_val  = row["close_vix"]
        atr      = row["atr"]
        score    = int(row["score"])
        vix_chg  = row["vix_chg_1d"]
        roc1     = row["roc1"]
        week     = row["week_key"]
        dow      = row["day_of_week"]
        regime   = row["regime"]

        vix_20      = row.get("vix_20d_avg", 15.0)
        velocity    = row.get("velocity", 0.0)
        vix_ceiling = vix_bands(vix_20)

        if velocity > VELOCITY_THRESHOLD and score >= 1:
            v19_velocity_blocked = True
        else:
            v19_velocity_blocked = False

        if vix_val >= 25: continue
        if vix_chg > VIX_SPIKE_SUPPRESS: continue
        if row["open_gap_pct"] > 0.8: continue

        vix_5d_std = row["vix_5d_std"] if not np.isnan(row["vix_5d_std"]) else 99
        vix_stb    = vix_5d_std < 1.5

        bull_bias = (row["ema20"] > row["ema50"]) and (row["close"] > row["ema50"]) and (row["roc5"] > 0.5)
        bear_bias = (row["ema20"] < row["ema50"]) and (row["close"] < row["ema50"]) and (row["roc5"] < -0.5)
        neut_bias = not bull_bias and not bear_bias
        dual_ok   = (vix_val < vix_ceiling) and (atr < 200)
        ultra_calm= (score == 0) and (vix_val < 12) and (atr < 150) and vix_stb

        weekly_cap = weekly_heat_cap(vix_val, atr, score)
        weekly_heat = sum(t.get("Risk", 0) for t in trades if t.get("Week") == week)

        entry_tier = None
        otm_dist   = 0.0

        # ── SAME PRIORITY WATERFALL AS BACKTEST ──────────────────────────
        vc_2d = row["vix_2d_chg"]
        if vc_2d < -15 and score < 3 and vix_val < vix_ceiling and atr < 250:
            adj = 700.0
            s = compute_safety(row, adj)
            if s >= SAFETY_FLOOR["VIX-Collapse"]:
                entry_tier, otm_dist = "VIX-Collapse", adj

        if not entry_tier and -15 <= vc_2d < -10 and score < 3 and vix_val < vix_ceiling:
            adj = 700.0
            s = compute_safety(row, adj)
            if s >= SAFETY_FLOOR["Near-VC"]:
                entry_tier, otm_dist = "Near-VC", adj

        if (not entry_tier and week not in used_butterfly and ultra_calm
                and atr <= BUTTERFLY_ATR_MAX and vix_val <= BUTTERFLY_VIX_MAX and score == 0):
            otm_b = 200.0
            s_p = compute_safety(row, otm_b, HOLD_DAYS_BUTTERFLY)
            s_c = compute_safety(row, otm_b, HOLD_DAYS_BUTTERFLY)
            if s_p >= SAFETY_FLOOR["Butterfly"] and s_c >= SAFETY_FLOOR["Butterfly"]:
                entry_tier, otm_dist = "Butterfly", otm_b

        if (not entry_tier and week not in used_thursday and dow == 3
                and score <= 1 and vix_val < 14 and atr < 100 and vix_val < vix_ceiling):
            adj = adaptive_otm(OTM_DIST_BASE["Thursday-EXP"], atr)
            s = compute_safety(row, adj, HOLD_DAYS_THURS)
            if s >= SAFETY_FLOOR["Thursday-EXP"]:
                entry_tier, otm_dist = "Thursday-EXP", float(adj)

        if (not entry_tier and (week + "_fri") not in used_layers
                and dow == 4 and score <= 1 and vix_val <= 14 and atr <= 130 and dual_ok):
            adj = adaptive_otm(OTM_DIST_BASE["Friday-SNP"], atr)
            s = compute_safety(row, adj, HOLD_DAYS_FRI)
            if s >= SAFETY_FLOOR["Friday-SNP"]:
                entry_tier, otm_dist = "Friday-SNP", float(adj)

        if (not entry_tier and (week + "_mon") not in used_layers and not v19_velocity_blocked
                and dow == 0 and score <= 1 and vix_val < 16 and atr <= 160 and dual_ok):
            adj = adaptive_otm(OTM_DIST_BASE["Monday-RW"], atr)
            s = compute_safety(row, adj)
            if s >= SAFETY_FLOOR["Monday-RW"]:
                entry_tier, otm_dist = "Monday-RW", float(adj)

        if (not entry_tier and (week + "_wed") not in used_layers and not v19_velocity_blocked
                and dow == 2 and score <= 1 and vix_val < vix_ceiling and atr <= 180):
            adj = adaptive_otm(OTM_DIST_BASE["Wednesday-MW"], atr)
            s = compute_safety(row, adj)
            if s >= SAFETY_FLOOR["Wednesday-MW"]:
                entry_tier, otm_dist = "Wednesday-MW", float(adj)

        if (not entry_tier and week not in used_condor and neut_bias
                and score <= 1 and atr <= NARROW_CONDOR_ATR_MAX
                and vix_val <= NARROW_CONDOR_VIX_MAX and vix_stb):
            otm_n = 400.0
            s_bp = compute_safety(row, otm_n)
            s_bc = compute_safety(row, otm_n)
            if s_bp >= SAFETY_FLOOR["NarrowCondor-BP"] and s_bc >= SAFETY_FLOOR["NarrowCondor-BC"]:
                entry_tier, otm_dist = "NarrowCondor", otm_n

        if (not entry_tier and (week + "_wed") not in used_layers and neut_bias
                and score <= 2 and CONDOR_VIX_MIN <= vix_val <= CONDOR_VIX_MAX
                and CONDOR_ATR_MIN <= atr <= CONDOR_ATR_MAX and vix_stb and dual_ok):
            put_leg = float(450 if roc1 > 0.3 else 500)
            call_leg = float(450 if roc1 < -0.3 else 500)
            put_leg = float(adaptive_otm(put_leg, atr))
            call_leg = float(adaptive_otm(call_leg, atr))
            s_bp = compute_safety(row, put_leg)
            s_bc = compute_safety(row, call_leg)
            if s_bp >= SAFETY_FLOOR["Condor-BP"] and s_bc >= SAFETY_FLOOR["Condor-BC"]:
                entry_tier, otm_dist = "CONDOR", put_leg

        if (not entry_tier and (week + "_wed") not in used_layers and neut_bias
                and score <= 2 and WIDE_CONDOR_ATR_MIN <= atr <= WIDE_CONDOR_ATR_MAX
                and vix_val < 20 and vix_stb):
            otm_w = 600.0
            s_bp = compute_safety(row, otm_w)
            s_bc = compute_safety(row, otm_w)
            if s_bp >= SAFETY_FLOOR["WideCondor-BP"] and s_bc >= SAFETY_FLOOR["WideCondor-BC"]:
                entry_tier, otm_dist = "WideCondor", otm_w

        if (not entry_tier
                and (week + ("_mon" if dow==0 else "_wed" if dow==2 else "_fri")) not in used_layers
                and bear_bias and score <= 2 and atr <= 200 and vix_val < vix_ceiling and dual_ok):
            adj = float(adaptive_otm(OTM_DIST_BASE["Bear-Call"], atr))
            s = compute_safety(row, adj)
            if s >= SAFETY_FLOOR["Bear-Call"]:
                entry_tier, otm_dist = "Bear-Call", adj

        if not entry_tier and (week + ("_mon" if dow==0 else "_wed" if dow==2 else "_fri")) not in used_layers and not v19_velocity_blocked:
            if score == 0 and atr < 150 and vix_val < 12 and vix_stb and dual_ok and atr < HIGH_ATR_MIN:
                adj = float(adaptive_otm(OTM_DIST_BASE["Aggressive"], atr))
                s = compute_safety(row, adj)
                if s >= SAFETY_FLOOR["Aggressive"]:
                    entry_tier, otm_dist = "Aggressive", adj
            elif score < 3 and atr <= 180 and vix_val < vix_ceiling and vix_stb and dual_ok and atr < HIGH_ATR_MIN:
                adj = float(adaptive_otm(OTM_DIST_BASE["Normal"], atr))
                s = compute_safety(row, adj)
                if s >= SAFETY_FLOOR["Normal"]:
                    entry_tier, otm_dist = "Normal", adj
            elif score < 3 and atr <= 250 and atr < HIGH_ATR_MIN:
                adj = float(adaptive_otm(OTM_DIST_BASE["Cautious"], atr))
                s = compute_safety(row, adj)
                if s >= SAFETY_FLOOR["Cautious"]:
                    entry_tier, otm_dist = "Cautious", adj

        if (not entry_tier and HIGH_ATR_MIN <= atr <= HIGH_ATR_MAX
                and vix_val < 20 and score < 3):
            s = compute_safety(row, 750.0)
            if s >= SAFETY_FLOOR["HighATR-Cautious"]:
                entry_tier, otm_dist = "HighATR-Cautious", 750.0

        if not entry_tier:
            continue

        # ── Determine hold days ──────────────────────────────────────────
        if entry_tier == "Thursday-EXP": hd = HOLD_DAYS_THURS
        elif entry_tier == "Friday-SNP": hd = HOLD_DAYS_FRI
        elif entry_tier == "Butterfly":  hd = HOLD_DAYS_BUTTERFLY
        else: hd = HOLD_DAYS

        hold_slice = df.iloc[i + 1: i + hd + 1]
        if len(hold_slice) < 1:
            continue

        safety = compute_safety(row, otm_dist, hd)

        base_tier = entry_tier.replace("NarrowCondor", "NarrowCondor-BP").replace("WideCondor", "WideCondor-BP")
        risk_this = SPREAD_WIDTH - PREMIUM_BASE.get(base_tier, PREMIUM_BASE.get("Normal", 60))
        if entry_tier in ("CONDOR", "NarrowCondor", "WideCondor", "Butterfly"):
            risk_this *= 2
        if weekly_heat + risk_this > weekly_cap:
            continue

        # ── NOW THE REAL AUDIT: check actual intraday breach ─────────────
        entry_close = row["close"]
        is_condor = entry_tier in ("CONDOR", "NarrowCondor", "WideCondor")
        is_butterfly = entry_tier == "Butterfly"
        is_bear_call = entry_tier == "Bear-Call"

        # Build list of legs to check
        legs = []
        if is_condor:
            if entry_tier == "CONDOR":
                put_otm = float(adaptive_otm(float(450 if roc1 > 0.3 else 500), atr))
                call_otm = float(adaptive_otm(float(450 if roc1 < -0.3 else 500), atr))
            else:
                put_otm = call_otm = otm_dist
            legs.append(("Bull Put",  entry_close - put_otm,  put_otm, False))
            legs.append(("Bear Call", entry_close + call_otm, call_otm, True))
        elif is_butterfly:
            legs.append(("Bull Put",  entry_close - otm_dist, otm_dist, False))
            legs.append(("Bear Call", entry_close + otm_dist, otm_dist, True))
        elif is_bear_call:
            legs.append(("Bear Call", entry_close + otm_dist, otm_dist, True))
        else:
            legs.append(("Bull Put",  entry_close - otm_dist, otm_dist, False))

        for side_label, short_strike, leg_otm, is_call_side in legs:
            # Backtest method: check CLOSE only
            close_breached = False
            close_breach_day = None
            # REAL method: check HIGH (for bear call) or LOW (for bull put)
            intraday_breached = False
            intraday_breach_day = None
            closest_approach_pts = float('inf')
            closest_approach_day = None

            for day_idx, (_, bar) in enumerate(hold_slice.iterrows(), start=1):
                close_px = bar["close"]
                low_px   = bar["low"]
                high_px  = bar["high"]

                if is_call_side:
                    # Bear call: breach if price goes UP to short strike
                    dist_to_strike = short_strike - high_px  # positive = safe
                    if close_px >= short_strike and not close_breached:
                        close_breached = True
                        close_breach_day = day_idx
                    if high_px >= short_strike and not intraday_breached:
                        intraday_breached = True
                        intraday_breach_day = day_idx
                else:
                    # Bull put: breach if price goes DOWN to short strike
                    dist_to_strike = low_px - short_strike  # positive = safe
                    if close_px <= short_strike and not close_breached:
                        close_breached = True
                        close_breach_day = day_idx
                    if low_px <= short_strike and not intraday_breached:
                        intraday_breached = True
                        intraday_breach_day = day_idx

                if dist_to_strike < closest_approach_pts:
                    closest_approach_pts = dist_to_strike
                    closest_approach_day = day_idx

            trades.append({
                "Date": curr_date,
                "Tier": entry_tier,
                "Side": side_label,
                "Entry": round(entry_close, 1),
                "ShortStrike": round(short_strike, 1),
                "OTM": int(leg_otm),
                "HoldDays": hd,
                "ActualBars": len(hold_slice),
                "Safety%": round(safety, 1),
                "VIX": round(vix_val, 2),
                "ATR": round(atr, 1),
                "Score": score,
                "ClosestApproach": round(closest_approach_pts, 1),
                "ClosestDay": closest_approach_day,
                "CloseBreached": close_breached,
                "CloseBDay": close_breach_day,
                "IntradayBreached": intraday_breached,
                "IntradayBDay": intraday_breach_day,
                "Week": week,
                "Risk": round(risk_this, 1),
                "Year": curr_date.year,
            })

        # Deduplication (same as backtest)
        if entry_tier in ("Aggressive", "Normal", "Cautious", "Bear-Call", "Monday-RW", "Wednesday-MW", "Friday-SNP"):
            used_layers.add(week + ("_mon" if dow==0 else "_wed" if dow==2 else "_fri"))
        elif entry_tier == "Tuesday-LV":
            used_tuesday.add(week)
        elif entry_tier == "Thursday-EXP":
            used_thursday.add(week)
        elif "Condor" in entry_tier or entry_tier == "CONDOR":
            used_condor.add(week)
        elif entry_tier == "Butterfly":
            used_butterfly.add(week)

        # Circuit breaker check (use close-only breach for consistency with backtest)
        if close_breached:
            circuit_breaker_until = curr_date + timedelta(days=3)

    # ── PRINT RESULTS ────────────────────────────────────────────────────
    results = pd.DataFrame(trades)
    if results.empty:
        print("No trades generated!")
        return

    total_legs = len(results)
    close_breaches = results["CloseBreached"].sum()
    intraday_breaches = results["IntradayBreached"].sum()

    print("=" * 80)
    print("  STRIKE BREACH AUDIT — SpreadGuard V2024")
    print("=" * 80)
    print(f"  Period           : {results['Date'].min().date()} → {results['Date'].max().date()}")
    print(f"  Total Trade Legs : {total_legs}")
    print()
    print(f"  ── BREACH RESULTS ────────────────────────────────────")
    print(f"  Close-Only Breaches (what backtest checks) : {close_breaches} / {total_legs}  ({close_breaches/total_legs*100:.1f}%)")
    print(f"  Intraday Breaches  (HIGH/LOW reality)      : {intraday_breaches} / {total_legs}  ({intraday_breaches/total_legs*100:.1f}%)")
    print(f"  Hidden Losses (intraday hit but close OK)  : {intraday_breaches - close_breaches}")
    print()

    # Win rate comparison
    close_wr = (total_legs - close_breaches) / total_legs * 100
    intraday_wr = (total_legs - intraday_breaches) / total_legs * 100
    print(f"  ── WIN RATE COMPARISON ───────────────────────────────")
    print(f"  Close-Only Win Rate   : {close_wr:.1f}%")
    print(f"  Intraday Win Rate     : {intraday_wr:.1f}%")
    print()

    # Closest approach stats
    print(f"  ── CLOSEST APPROACH STATISTICS ───────────────────────")
    print(f"  Min closest approach  : {results['ClosestApproach'].min():.0f} pts  ← most dangerous trade")
    print(f"  5th percentile        : {results['ClosestApproach'].quantile(0.05):.0f} pts")
    print(f"  10th percentile       : {results['ClosestApproach'].quantile(0.10):.0f} pts")
    print(f"  Median                : {results['ClosestApproach'].quantile(0.50):.0f} pts")
    print(f"  Mean                  : {results['ClosestApproach'].mean():.0f} pts")
    print()

    # Trades where market came within 100 pts of strike
    close_calls = results[results["ClosestApproach"] < 100]
    print(f"  ── CLOSE CALLS (market came within 100 pts of strike) ──")
    print(f"  Count: {len(close_calls)} / {total_legs}")
    if len(close_calls) > 0:
        print(f"\n  {'Date':<12} {'Tier':<18} {'Side':<10} {'Entry':>8} {'Strike':>8} {'OTM':>5} {'Closest':>8} {'Day':>4} {'VIX':>6} {'ATR':>6} {'Breach?'}")
        print(f"  {'─'*110}")
        for _, t in close_calls.sort_values("ClosestApproach").iterrows():
            breach_tag = "INTRADAY!" if t["IntradayBreached"] else ("CLOSE!" if t["CloseBreached"] else "survived")
            print(f"  {str(t['Date'].date()):<12} {t['Tier']:<18} {t['Side']:<10} "
                  f"{t['Entry']:>8.0f} {t['ShortStrike']:>8.0f} {t['OTM']:>5} "
                  f"{t['ClosestApproach']:>8.0f} {t['ClosestDay']:>4} "
                  f"{t['VIX']:>6.1f} {t['ATR']:>6.0f} {breach_tag}")

    print()

    # Per-tier breach summary
    print(f"  ── PER-TIER BREACH SUMMARY ───────────────────────────")
    print(f"  {'Tier':<20} {'Legs':>6} {'CloseB':>7} {'IntraB':>7} {'MinAppr':>8} {'AvgAppr':>8}")
    print(f"  {'─'*62}")
    for tier, grp in results.groupby("Tier"):
        print(f"  {tier:<20} {len(grp):>6} {grp['CloseBreached'].sum():>7} "
              f"{grp['IntradayBreached'].sum():>7} "
              f"{grp['ClosestApproach'].min():>8.0f} {grp['ClosestApproach'].mean():>8.0f}")

    print()

    # Per-year breach summary
    print(f"  ── PER-YEAR BREACH COUNT ─────────────────────────────")
    print(f"  {'Year':<6} {'Legs':>6} {'CloseB':>7} {'IntraB':>7} {'MinApproach':>12}")
    print(f"  {'─'*42}")
    for yr, grp in results.groupby("Year"):
        print(f"  {yr:<6} {len(grp):>6} {grp['CloseBreached'].sum():>7} "
              f"{grp['IntradayBreached'].sum():>7} {grp['ClosestApproach'].min():>12.0f}")

    print()

    # Danger zone: trades where approach < OTM * 0.5
    danger = results[results["ClosestApproach"] < results["OTM"] * 0.5]
    print(f"  ── DANGER ZONE (market moved >50% toward strike) ────")
    print(f"  Count: {len(danger)} / {total_legs}  ({len(danger)/total_legs*100:.1f}%)")
    if len(danger) > 0:
        print(f"\n  {'Date':<12} {'Tier':<18} {'Side':<10} {'OTM':>5} {'Closest':>8} {'MovedPct':>8} {'VIX':>6}")
        print(f"  {'─'*80}")
        for _, t in danger.sort_values("ClosestApproach").head(20).iterrows():
            moved_pct = (1 - t["ClosestApproach"] / t["OTM"]) * 100
            print(f"  {str(t['Date'].date()):<12} {t['Tier']:<18} {t['Side']:<10} "
                  f"{t['OTM']:>5} {t['ClosestApproach']:>8.0f} {moved_pct:>7.1f}% {t['VIX']:>6.1f}")

    print()
    print("=" * 80)

    # Save full results
    results.to_csv("strike_breach_audit.csv", index=False)
    print(f"  Full results → strike_breach_audit.csv")
    print("=" * 80)


if __name__ == "__main__":
    run_breach_audit()
