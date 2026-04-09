import streamlit as st
import pandas as pd
import requests
import json
import os
import time
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# 1. PAGE CONFIG & STYLING (Institutional Dark)
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="NIFTY SpreadGuard V2024 | Strategic Husk",
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
        transition: transform 0.2s;
    }
    .status-active-safe { border-left: 5px solid #00FF85; box-shadow: 0 0 10px rgba(0,255,133,0.1); }
    .status-active-danger { border-left: 5px solid #FFD700; box-shadow: 0 0 10px rgba(255,215,0,0.1); }
    .status-inactive { border-left: 5px solid #2D3436; opacity: 0.4; pointer-events: none;}
    
    .tier-title { font-size: 1.1rem; font-weight: bold; margin-bottom: 5px; color: #FFF; }
    .tier-meta { font-size: 0.85rem; color: #888; }
    .active-badge { background-color: #00FF85; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; margin-left: 10px;}
    .agg-badge { background-color: #FFD700; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; margin-left: 10px;}
    </style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# 2. STATE LOADER (FETCHING FROM CLOUD)
# ─────────────────────────────────────────────────────────────────────────────

RAW_URL = "https://raw.githubusercontent.com/pravindev666/SpreadGuard-V24-Algorithmic-Nifty-Options-Engine/main/data/intelligence_pulse.json"

@st.cache_data(ttl=15)
def fetch_pulse(mode):
    if mode == "📡 LIVE CLOUD (GITHUB)":
        try:
            response = requests.get(RAW_URL)
            if response.status_code == 200:
                return response.json()
        except: pass
        return None
    else:
        path = "data/intelligence_pulse.json"
        if os.path.exists(path):
            with open(path, "r") as f: return json.load(f)
        return None

# ─────────────────────────────────────────────────────────────────────────────
# 3. SIDEBAR: AWARENESS SENSORS
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🛡️ SENSOR HUB")
    mode = st.radio("Sync Source", ["📡 LIVE CLOUD (GITHUB)", "🏠 LOCAL DISK"])
    st.divider()
    
    pulse = fetch_pulse(mode)
    if pulse:
        m = pulse.get("market", {})
        i = pulse.get("intelligence", {})
        
        st.caption(f"Heartbeat: {pulse.get('timestamp', 'Unknown')}")
        
        # Primary Danger Matrix (96% Backtest Rules)
        st.markdown("### Decision Engine (Backtest)")
        d_score = i.get("danger_score", 0)
        v_veto = i.get("vwap_veto", False)
        v_ceil = i.get("vix_threshold", 20.0)
        cur_vix = m.get("vix", 0)

        st.metric("Danger Score", f"{d_score}/4", delta="VETO" if v_veto else "CLEAR", delta_color="inverse" if v_veto else "normal")
        st.metric("VIX Ceiling", f"{v_ceil:.1f}", delta=f"{cur_vix:.1f} (ACT)", delta_color="inverse" if cur_vix > v_ceil else "normal")
        
        st.divider()
        
        # Secondary Awareness (HUD Indicators)
        st.markdown("### Strategy Indicators")
        st.metric("Consensus", f"{i.get('consensus', 0)}/4 Match")
        st.caption(f"MTF Anchor: {i.get('anchor', 'N/A')}")
        st.caption(f"Bias: {i.get('bias', 'N/A')}")
    else:
        st.error("Backend Disconnected.")

# ─────────────────────────────────────────────────────────────────────────────
# 4. STRATEGIC RADAR
# ─────────────────────────────────────────────────────────────────────────────

if pulse:
    st.title("🎯 SpreadGuard All-Tiers Radar")
    
    # Global Cockpit
    m = pulse["market"]
    v1, v2, v3, v4, v5 = st.columns(5)
    v1.metric("NIFTY SPOT", f"{m['spot']:,.2f}")
    v2.metric("INDIA VIX", f"{m['vix']:.2f}")
    v3.metric("ATR (14d)", f"{m['atr']:.1f}")
    v4.metric("VELOCITY", f"{m['velocity']:.2f}%")
    v5.metric("5d ROC", f"{m['roc5']:.2f}%")
    
    st.divider()
    
    col_safe, col_agg = st.columns(2)
    tiers = pulse["tiers"]
    
    with col_safe:
        st.subheader("🟢 HIGH CONVICTION [96% W/R]")
        st.caption("Restricted to lowest volatility regimes. Mandatory for large capital.")
        
        for t in [x for x in tiers if x["safe"]]:
            status_cls = "status-active-safe" if t["active"] else "status-inactive"
            badge = f"<span class='active-badge'>ACTIVE</span>" if t["active"] else ""
            
            # Auto-calculate strike for display
            strike_txt = ""
            if t["active"]:
                base_spot = m["spot"]
                if t["type"] == "Bull Put":
                    strike = int(round((base_spot - t["otm"]) / 50) * 50)
                    strike_txt = f"Sell {strike} PE"
                elif t["type"] == "Iron Fly":
                    strike = int(round(base_spot / 50) * 50)
                    strike_txt = f"Sell {strike} Fly"
            
            st.markdown(f"""
            <div class='tier-card {status_cls}'>
                <div class='tier-title'>{t['name']} {badge}</div>
                <div class='tier-meta' style='color: #00FF85;'>{strike_txt if t['active'] else 'Conditions Suspended'}</div>
                <div class='tier-meta'>Rule: BP {t['otm']} pts OTM | Strategy: {t['type']}</div>
            </div>
            """, unsafe_allow_html=True)

    with col_agg:
        st.subheader("🟡 AGGRESSIVE / REGIME")
        st.caption("Strategic directional plays. Expect occasional drawdown cycles.")
        
        for t in [x for x in tiers if not x["safe"]]:
            status_cls = "status-active-danger" if t["active"] else "status-inactive"
            badge = f"<span class='agg-badge'>ACTIVE</span>" if t["active"] else ""
            
            strike_txt = ""
            if t["active"]:
                base_spot = m["spot"]
                if t["type"] == "Bull Put":
                    strike = int(round((base_spot - t["otm"]) / 50) * 50)
                    strike_txt = f"Sell {strike} PE"
                elif t["type"] == "Bear Call":
                    strike = int(round((base_spot + t["otm"]) / 50) * 50)
                    strike_txt = f"Sell {strike} CE"
                elif t["type"] == "Iron Condor":
                    sp = int(round((base_spot - t["otm"]) / 50) * 50)
                    sc = int(round((base_spot + t["otm"]) / 50) * 50)
                    strike_txt = f"Sell {sp} PE / {sc} CE"
            
            st.markdown(f"""
            <div class='tier-card {status_cls}'>
                <div class='tier-title'>{t['name']} {badge}</div>
                <div class='tier-meta' style='color: #FFD700;'>{strike_txt if t['active'] else 'Waiting for Bias'}</div>
                <div class='tier-meta'>Buffer: {t['otm']} pts | Strategy: {t['type']}</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    st.markdown("### 📋 Verification Summary")
    st.info(f"System following **V2024-Backtest-Hardened** protocol. Backend Pulse v2.0.")

# ── AUTO REFRESH LOOP ──
time.sleep(15)
st.rerun()
