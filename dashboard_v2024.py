import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm
import os
import time
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# 1. PAGE CONFIG & STYLING
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="NIFTY SpreadGuard V2024 | All-Tiers Radar",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;700&display=swap');
    html, body, [class*="css"] { font-family: 'JetBrains+Mono', monospace; color: #E0E0E0; }
    .main { background-color: #0A0C0E; }
    [data-testid="stSidebar"] { background-color: #121518; border-right: 1px solid #1F2428; }
    
    .tier-card {
        background: rgba(16, 20, 24, 0.9);
        border: 1px solid #2D3436;
        border-radius: 6px;
        padding: 15px;
        margin-bottom: 15px;
    }
    .status-active-safe { border-left: 4px solid #00FF85; }
    .status-active-danger { border-left: 4px solid #FF4B2B; opacity: 0.9; }
    .status-inactive { border-left: 4px solid #2D3436; opacity: 0.5; }
    
    .tier-title { font-size: 1.2rem; font-weight: bold; margin-bottom: 5px; }
    .tier-meta { font-size: 0.9rem; color: #888; }
    .active-badge { background-color: #00FF85; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; font-weight: bold;}
    .danger-badge { background-color: #FF4B2B; color: #FFF; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; font-weight: bold;}
    </style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# 2. AUTOMATED SENSOR ENGINE
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_and_calc_v2(nifty_path, vix_path):
    if not os.path.exists(nifty_path) or not os.path.exists(vix_path):
        return None
    
    n_raw = pd.read_csv(nifty_path, parse_dates=['date']).tail(2000)
    v_raw = pd.read_csv(vix_path, parse_dates=['date']).tail(2000)
    
    n_raw.set_index('date', inplace=True)
    v_raw.set_index('date', inplace=True)
    
    # Simple forward fill and align
    n_raw = n_raw[~n_raw.index.duplicated(keep='last')]
    v_raw = v_raw[~v_raw.index.duplicated(keep='last')]
    
    # 1. 14d ATR
    pc = n_raw['close'].shift(1)
    tr = np.maximum(n_raw['high'] - n_raw['low'], 
                    np.maximum(abs(n_raw['high'] - pc), abs(n_raw['low'] - pc)))
    atr_val = tr.ewm(alpha=1/14, adjust=False).mean().iloc[-1]
    
    # 2. Daily ROC
    roc1 = n_raw['close'].pct_change(1) * 100
    velocity = roc1.abs().rolling(3).sum().iloc[-1]
    roc5 = n_raw['close'].pct_change(5).iloc[-1] * 100
    
    # 3. EMA 20/50
    ema20 = n_raw['close'].ewm(span=20, adjust=False).mean().iloc[-1]
    ema50 = n_raw['close'].ewm(span=50, adjust=False).mean().iloc[-1]
    
    # 4. VIX Changes
    vix_chg_1d = (v_raw['close'].iloc[-1] - v_raw['close'].iloc[-2]) / v_raw['close'].iloc[-2] * 100
    vix_2d_chg = (v_raw['close'].iloc[-1] - v_raw['close'].iloc[-3]) / v_raw['close'].iloc[-3] * 100
    vix_5d_std = v_raw['close'].rolling(5).std().iloc[-1]
    vix_20d_avg = v_raw['close'].rolling(20).mean().iloc[-1]
    
    # Danger Score Calculation from Backtest
    # Uses 18 for VIX as per backtest, not 20
    score = 0
    score += (1 if v_raw['close'].iloc[-1] > 18 else 0)
    score += (1 if vix_chg_1d > 15 else 0)
    score += (1 if atr_val > 200 else 0)
    score += (1 if abs(roc5) > 2.0 else 0)
    
    return {
        "spot": n_raw['close'].iloc[-1],
        "vix": v_raw['close'].iloc[-1],
        "atr": atr_val,
        "velocity": velocity,
        "ema20": ema20,
        "ema50": ema50,
        "roc5": roc5,
        "roc1": roc1.iloc[-1],
        "score": score,
        "vix_chg_1d": vix_chg_1d,
        "vix_2d_chg": vix_2d_chg,
        "vix_5d_std": vix_5d_std,
        "vix_20d_avg": vix_20d_avg,
        "time": n_raw.index[-1],
        "dow_idx": n_raw.index[-1].weekday(),  # 0=Mon, 4=Fri
        "dow": n_raw.index[-1].strftime("%A")
    }

def get_nifty_expiry(ref_date):
    target = ref_date + timedelta(days=(1 - ref_date.weekday() + 7) % 7)
    if (target - ref_date).days < 6:
        target += timedelta(days=7)
    return target.strftime("%d %b (Tuesday)")

def adaptive_otm(base, current_atr):
    ratio = max(0.9, min(1.1, current_atr / 150.0))
    return int(round(base * ratio / 50) * 50)

# ─────────────────────────────────────────────────────────────────────────────
# 3. SIDEBAR & SENSORS
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🎯 SNIPER SENSORS")
    source = st.radio("Intelligence Source", ["📡 CSV AUTO-FEED", "⌨️ MANUAL ENTRY"])
    
    st.divider()
    
    if source == "📡 CSV AUTO-FEED":
        n_path = st.text_input("Nifty Daily Path", "data/nifty_daily.csv")
        v_path = st.text_input("VIX Daily Path", "data/vix_daily.csv")
        
        data = load_and_calc_v2(n_path, v_path)
        if data:
            st.success(f"Sniper Ready: {data['time'].strftime('%Y-%m-%d')} ({data['dow']})")
            st.metric("Danger Score", f"{data['score']}/6", delta="Elevated" if data['score'] >= 2 else "Normal")
        else:
            st.error("Check data/ folder files!")
            source = "⌨️ MANUAL ENTRY"
            data = None
            
    if source == "⌨️ MANUAL ENTRY" or data is None:
        data = {
            "spot": st.number_input("Nifty Spot", 15000, 35000, 22200),
            "vix": st.number_input("India VIX", 8.0, 40.0, 14.5, 0.1),
            "atr": st.number_input("14d ATR", 50.0, 500.0, 155.0, 1.0),
            "velocity": st.number_input("3-Day Velocity (%)", 0.0, 15.0, 1.2, 0.1),
            "ema20": st.number_input("EMA 20", 15000.0, 35000.0, 22100.0),
            "ema50": st.number_input("EMA 50", 15000.0, 35000.0, 21800.0),
            "roc5": st.slider("5-Day ROC (%)", -5.0, 5.0, 1.2, 0.1),
            "roc1": 0.5,
            "score": st.slider("Danger Score (0-6)", 0, 6, 0),
            "dow": st.selectbox("Day of Week", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]),
            "vix_chg_1d": 0.0,
            "vix_2d_chg": 0.0,
            "vix_5d_std": 1.0,
            "vix_20d_avg": 15.0,
            "time": datetime.now()
        }
        dow_map = {"Monday":0, "Tuesday":1, "Wednesday":2, "Thursday":3, "Friday":4}
        data["dow_idx"] = dow_map[data["dow"]]

# ─────────────────────────────────────────────────────────────────────────────
# 4. ALL-TIERS EVALUATOR
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_tiers(d):
    vix = d["vix"]
    atr = d["atr"]
    score = d["score"]
    dow = d["dow_idx"]
    vix_20 = d["vix_20d_avg"]
    vix_ceiling = min(vix_20 * 1.15, 20.0)
    
    vix_stb = d["vix_5d_std"] < 1.5
    dual_ok = (vix < vix_ceiling) and (atr < 200)
    ultra_calm = (score == 0) and (vix < 12) and (atr < 150) and vix_stb
    
    bull_bias = (d["ema20"] > d["ema50"]) and (d["spot"] > d["ema50"]) and (d["roc5"] > 0.5)
    bear_bias = (d["ema20"] < d["ema50"]) and (d["spot"] < d["ema50"]) and (d["roc5"] < -0.5)
    neut_bias = not bull_bias and not bear_bias
    
    v19_velocity_blocked = (d["velocity"] > 3.5 and score >= 1)
    
    tiers = []
    
    # ── HIGH CONVICTION TIERS ──
    tf = (d["vix_2d_chg"] < -15 and score < 3 and vix < vix_ceiling and atr < 250)
    tiers.append({"name": "VIX-Collapse", "active": tf, "safe": True, "otm": 700, "type": "Bull Put"})
    
    tf = (-15 <= d["vix_2d_chg"] < -10 and score < 3 and vix < vix_ceiling)
    tiers.append({"name": "Near-VC", "active": tf, "safe": True, "otm": 700, "type": "Bull Put"})
    
    tf = (ultra_calm and atr <= 130 and vix <= 12 and score == 0)
    tiers.append({"name": "Butterfly", "active": tf, "safe": True, "otm": 200, "type": "Iron Fly"})
    
    tf = (dow == 3 and score <= 1 and vix < 14 and atr < 100 and vix < vix_ceiling)
    tiers.append({"name": "Thursday-EXP", "active": tf, "safe": True, "otm": adaptive_otm(600, atr), "type": "Bull Put"})
    
    tf = (dow == 4 and score <= 1 and vix <= 14 and atr <= 130 and dual_ok)
    tiers.append({"name": "Friday-SNP", "active": tf, "safe": True, "otm": adaptive_otm(640, atr), "type": "Bull Put"})
    
    tf = (not v19_velocity_blocked and dow == 0 and score <= 1 and vix < 16 and atr <= 160 and dual_ok)
    tiers.append({"name": "Monday-RW", "active": tf, "safe": True, "otm": adaptive_otm(680, atr), "type": "Bull Put"})
    
    tf = (not v19_velocity_blocked and dow == 2 and score <= 1 and vix < vix_ceiling and atr <= 180)
    tiers.append({"name": "Wednesday-MW", "active": tf, "safe": True, "otm": adaptive_otm(650, atr), "type": "Bull Put"})
    
    # ── AGGRESSIVE HIGH-FREQUENCY TIERS ──
    tf = (neut_bias and score <= 1 and atr <= 140 and vix <= 16 and vix_stb)
    tiers.append({"name": "NarrowCondor", "active": tf, "safe": False, "otm": 400, "type": "Iron Condor"})
    
    tf = (neut_bias and score <= 2 and 12 <= vix <= 20 and 120 <= atr <= 180 and vix_stb and dual_ok)
    tiers.append({"name": "CONDOR", "active": tf, "safe": False, "otm": adaptive_otm(500, atr), "type": "Iron Condor"})
    
    tf = (neut_bias and score <= 2 and 160 <= atr <= 200 and vix < 20 and vix_stb)
    tiers.append({"name": "WideCondor", "active": tf, "safe": False, "otm": 600, "type": "Iron Condor"})
    
    tf = (bear_bias and score <= 2 and atr <= 200 and vix < vix_ceiling and dual_ok)
    tiers.append({"name": "Bear-Call", "active": tf, "safe": False, "otm": adaptive_otm(600, atr), "type": "Bear Call"})
    
    tf = False
    if not v19_velocity_blocked:
        if score == 0 and atr < 150 and vix < 12 and vix_stb and dual_ok:
            tiers.append({"name": "Aggressive", "active": True, "safe": False, "otm": adaptive_otm(500, atr), "type": "Bull Put"})
        elif score < 3 and atr <= 180 and vix < vix_ceiling and vix_stb and dual_ok:
            tiers.append({"name": "Normal", "active": True, "safe": False, "otm": adaptive_otm(600, atr), "type": "Bull Put"})
        elif score < 3 and atr <= 250 and atr < 180:
            tiers.append({"name": "Cautious", "active": True, "safe": False, "otm": adaptive_otm(700, atr), "type": "Bull Put"})
            
    tf = (180 <= atr <= 240 and vix < 20 and score < 3)
    tiers.append({"name": "HighATR-Cautious", "active": tf, "safe": False, "otm": 750, "type": "Bull Put"})
    
    return tiers

all_tiers = evaluate_tiers(data)

# ─────────────────────────────────────────────────────────────────────────────
# 5. UI RENDERING
# ─────────────────────────────────────────────────────────────────────────────

st.title(f"🎯 SpreadGuard All-Tiers Radar")

# ─── SENSOR COCKPIT (VERIFICATION ROW) ───
v1, v2, v3, v4, v5 = st.columns(5)
v1.metric("NIFTY SPOT", f"{data['spot']:,.2f}")
v2.metric("INDIA VIX", f"{data['vix']:.2f}")
v3.metric("ATR (14d)", f"{data['atr']:.1f} pts")
v4.metric("VELOCITY", f"{data['velocity']:.2f}%")
v5.metric("5d ROC", f"{data['roc5']:.2f}%", delta=f"{'Bullish' if data['roc5'] > 0.5 else 'Bearish'}")

st.divider()

col_safe, col_danger = st.columns(2)

with col_safe:
    st.subheader("🟢 HIGH CONVICTION TIERS")
    st.markdown("*Ultra-safe, lowest volatility regimes. Highly recommended.*")
    safe_tiers = [t for t in all_tiers if t["safe"]]
    
    for t in safe_tiers:
        if t["active"]:
            if t["type"] == "Bull Put":
                short_strike = int(round((data["spot"] - t["otm"]) / 50) * 50)
                long_strike = short_strike - 200
                action_text = f"Strategy: {t['type']} | Sell {short_strike} PE, Buy {long_strike} PE"
            elif t["type"] == "Bear Call":
                short_strike = int(round((data["spot"] + t["otm"]) / 50) * 50)
                long_strike = short_strike + 200
                action_text = f"Strategy: {t['type']} | Sell {short_strike} CE, Buy {long_strike} CE"
            elif t["type"] == "Iron Fly":
                short_put = int(round((data["spot"] - t["otm"]) / 50) * 50)
                short_call = int(round((data["spot"] + t["otm"]) / 50) * 50)
                action_text = f"Strategy: {t['type']} | Sell {short_put} PE & {short_call} CE (wings 300 pts out)"
            elif t["type"] == "Iron Condor":
                short_put = int(round((data["spot"] - t["otm"]) / 50) * 50)
                short_call = int(round((data["spot"] + t["otm"]) / 50) * 50)
                action_text = f"Strategy: {t['type']} | Sell {short_put} PE & {short_call} CE (wings 200 pts out)"

            st.markdown(f"""
            <div class='tier-card status-active-safe'>
                <div class='tier-title'>{t["name"]} <span class='active-badge'>ACTIVE - GO</span></div>
                <div class='tier-meta' style='color: #00FF85;'>{action_text}</div>
                <div class='tier-meta'>Buffer: {t["otm"]} pts OTM</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class='tier-card status-inactive'>
                <div class='tier-title'>{t["name"]}</div>
                <div class='tier-meta'>Conditions not met</div>
            </div>
            """, unsafe_allow_html=True)

with col_danger:
    st.subheader("🟡 AGGRESSIVE TIERS")
    st.markdown("*Higher frequency trading. Intraday drawdown possible, but expected to recover by close.*")
    unsafe_tiers = [t for t in all_tiers if not t["safe"]]
    
    for t in unsafe_tiers:
        if t["active"]:
            if t["type"] == "Bull Put":
                short_strike = int(round((data["spot"] - t["otm"]) / 50) * 50)
                long_strike = short_strike - 200
                action_text = f"Strategy: {t['type']} | Sell {short_strike} PE, Buy {long_strike} PE"
            elif t["type"] == "Bear Call":
                short_strike = int(round((data["spot"] + t["otm"]) / 50) * 50)
                long_strike = short_strike + 200
                action_text = f"Strategy: {t['type']} | Sell {short_strike} CE, Buy {long_strike} CE"
            elif t["type"] == "Iron Fly":
                short_put = int(round((data["spot"] - t["otm"]) / 50) * 50)
                short_call = int(round((data["spot"] + t["otm"]) / 50) * 50)
                action_text = f"Strategy: {t['type']} | Sell {short_put} PE & {short_call} CE"
            elif t["type"] == "Iron Condor":
                short_put = int(round((data["spot"] - t["otm"]) / 50) * 50)
                short_call = int(round((data["spot"] + t["otm"]) / 50) * 50)
                action_text = f"Strategy: {t['type']} | Sell {short_put} PE & {short_call} CE"

            st.markdown(f"""
            <div class='tier-card status-active-safe'>
                <div class='tier-title'>{t["name"]} <span class='active-badge' style='background-color:#FFD700;color:#000;'>ACTIVE - GO</span></div>
                <div class='tier-meta' style='color: #FFD700;'>{action_text}</div>
                <div class='tier-meta'>Buffer: {t["otm"]} pts OTM</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class='tier-card status-inactive'>
                <div class='tier-title'>{t["name"]}</div>
                <div class='tier-meta'>Conditions not met</div>
            </div>
            """, unsafe_allow_html=True)

st.divider()

st.subheader("📋 Execution Rulebook (Safe Tiers Only)")
st.info(f"**Target Expiry:** {get_nifty_expiry(data['time'])}")
st.success(f"**Entry:** 11:30 AM | **Hold:** 1-7 Days depending on Tier")
st.markdown("""
**Risk Protocol:**
- **Max Layers:** Strict maximum 3 concurrent layers.
- **TP:** Exit manually on decay, or hold to expiry if perfectly calm.
- **Circuit Breaker:** Always honor a 3-day pause if a spread gets breached.
""")

# ── AUTO REFRESH LOOP ──
if source == "📡 CSV AUTO-FEED":
    time.sleep(30)
    st.rerun()
