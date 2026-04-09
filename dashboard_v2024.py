import streamlit as st
import pandas as pd
import requests
import json
import os
import time
from datetime import datetime

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
# 2. STATE LOADER (THE HUSK)
# ─────────────────────────────────────────────────────────────────────────────

RAW_URL = "https://raw.githubusercontent.com/pravindev666/SpreadGuard-V24-Algorithmic-Nifty-Options-Engine/main/data/intelligence_pulse.json"

@st.cache_data(ttl=15)
def fetch_pulse(mode):
    if mode == "📡 LIVE CLOUD (GITHUB)":
        try:
            response = requests.get(RAW_URL)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None
    else:
        path = "data/intelligence_pulse.json"
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return None

# ─────────────────────────────────────────────────────────────────────────────
# 3. SIDEBAR & SENSORS
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🎯 SNIPER SENSORS")
    st.markdown("*Headless Intelligence Engine*")
    
    mode = st.radio("Intelligence Mode", ["📡 LIVE CLOUD (GITHUB)", "🏠 LOCAL DISK"])
    
    st.divider()
    
    pulse = fetch_pulse(mode)
    
    if pulse:
        m = pulse["market"]
        i = pulse["intelligence"]
        
        st.success(f"Pulse Synced: {pulse['timestamp']}")
        
        # Danger Score / VIX Veto logic
        v_veto = i["vwap_veto"]
        d_score = i["score"]
        
        st.metric("Bias", i["bias"], delta="Stacked" if i["anchor"] == "BULL" else "Conflict")
        st.metric("Danger Score", f"{d_score}/4", delta="VETO" if v_veto else "SAFE", delta_color="inverse" if v_veto else "normal")
        
        st.divider()
        st.markdown("### Backend Attributes")
        st.json(i)
    else:
        st.error("Intelligence Engine Offline.")
        st.info("Run 'python intelligence_engine.py' locally or wait for GitHub Action.")

# ─────────────────────────────────────────────────────────────────────────────
# 5. UI RENDERING
# ─────────────────────────────────────────────────────────────────────────────

if pulse:
    m = pulse["market"]
    i = pulse["intelligence"]
    s = pulse["strikes"]

    st.title(f"🎯 SpreadGuard All-Tiers Radar")
    
    # ─── SENSOR COCKPIT ───
    v1, v2, v3, v4, v5 = st.columns(5)
    v1.metric("NIFTY SPOT", f"{m['spot']:,.2f}")
    v2.metric("INDIA VIX", f"{m['vix']:.2f}")
    v3.metric("ATR (14d)", f"{m['atr']:.1f} pts")
    v4.metric("VELOCITY", f"{m['velocity']:.2f}%")
    v5.metric("5d ROC", f"{m['roc5']:.2f}%", delta=f"{'Bullish' if m['roc5'] > 0 else 'Bearish'}")
    
    st.divider()
    
    col_safe, col_danger = st.columns(2)
    
    # Simple Logic for Display (Matches backtest/intelligence engine)
    is_safe_regime = (not i["vwap_veto"]) and (i["score"] >= 2) and (not i["shock"])
    
    with col_safe:
        st.subheader("🟢 HIGH CONVICTION TIERS")
        
        # VIX Collapse Card
        tf = (i["bias"] == "STRONG BULL" and i["anchor"] == "BULL" and not i["vwap_veto"])
        status_cls = "status-active-safe" if tf else "status-inactive"
        badge = "<span class='active-badge'>ACTIVE - GO</span>" if tf else ""
        
        st.markdown(f"""
        <div class='tier-card {status_cls}'>
            <div class='tier-title'>VIX-Collapse {badge}</div>
            <div class='tier-meta' style='color: #00FF85;'>Strategy: Bull Put | Sell {s['bp_700']} PE</div>
            <div class='tier-meta'>Target Buffer: 700 pts OTM</div>
        </div>
        """, unsafe_allow_html=True)

        # Sniper Tier
        tf = (is_safe_regime and i["anchor"] == "BULL")
        status_cls = "status-active-safe" if tf else "status-inactive"
        badge = "<span class='active-badge'>ACTIVE - GO</span>" if tf else ""
        st.markdown(f"""
        <div class='tier-card {status_cls}'>
            <div class='tier-title'>Sniper-Elite {badge}</div>
            <div class='tier-meta' style='color: #00FF85;'>Strategy: Bull Put | Sell {s['bp_500']} PE</div>
            <div class='tier-meta'>Target Buffer: 500 pts OTM</div>
        </div>
        """, unsafe_allow_html=True)

    with col_danger:
        st.subheader("🟡 AGGRESSIVE TIERS")
        
        # Condor
        tf = (not i["shock"] and abs(m["roc1"]) < 1.0)
        status_cls = "status-active-safe" if tf else "status-inactive"
        badge = "<span class='active-badge' style='background-color:#FFD700;color:#000;'>ACTIVE - GO</span>" if tf else ""
        st.markdown(f"""
        <div class='tier-card {status_cls}'>
            <div class='tier-title'>Condor-Harvest {badge}</div>
            <div class='tier-meta' style='color: #FFD700;'>Strategy: Iron Condor | Sell {s['bp_500']} PE & {s['bc_500']} CE</div>
            <div class='tier-meta'>Range: 500-pt Symmetrical</div>
        </div>
        """, unsafe_allow_html=True)

        # Bear Tier
        tf = (i["bias"].contains("BEAR") if hasattr(i["bias"], "contains") else "BEAR" in i["bias"])
        status_cls = "status-active-danger" if tf else "status-inactive"
        badge = "<span class='danger-badge'>BEAR THREAT</span>" if tf else ""
        st.markdown(f"""
        <div class='tier-card {status_cls}'>
            <div class='tier-title'>Bear-Call-Offense {badge}</div>
            <div class='tier-meta' style='color: #FF4B2B;'>Strategy: Bear Call | Sell {s['bc_500']} CE</div>
            <div class='tier-meta'>Aggressive Directional Sell</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()
    st.subheader("📋 Execution Rulebook (Headless Sync)")
    st.info(f"**Last Sync:** {pulse['timestamp']} | **Engine Version:** 2024.Elite")
    st.warning("⚠️ ALWAYS check the 'VWAP VETO' sensor. If Veto is ON, all Bull Puts are blocked.")

# ── AUTO REFRESH LOOP ──
time.sleep(15)
st.rerun()
