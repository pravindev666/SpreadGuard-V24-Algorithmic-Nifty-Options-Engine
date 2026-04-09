import streamlit as st
import pandas as pd
import requests
import json
import os
import time
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# 1. PAGE CONFIG & PURE DARK THEME
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
        background: #101418;
        border: 1px solid #1F2428;
        border-radius: 4px;
        padding: 12px;
        margin-bottom: 8px;
    }
    .status-active-safe { border-left: 4px solid #00FF85; }
    .status-active-danger { border-left: 4px solid #FFD700; }
    .status-inactive { border-left: 4px solid #2D3436; color: #4F565E; }
    
    .tier-title { font-size: 1.0rem; font-weight: bold; }
    .tier-meta { font-size: 0.8rem; }
    .active-badge { background-color: #00FF85; color: #000; padding: 1px 5px; border-radius: 3px; font-size: 0.7rem; font-weight: bold; margin-left: 8px;}
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
            if response.status_code == 200: return response.json()
        except: pass
        return None
    else:
        path = "data/intelligence_pulse.json"
        if os.path.exists(path):
            with open(path, "r") as f: return json.load(f)
        return None

# ─────────────────────────────────────────────────────────────────────────────
# 3. SIDEBAR: DATA INTEGRITY
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🛡️ SENSOR HUB")
    mode = st.radio("Sync Source", ["📡 LIVE CLOUD (GITHUB)", "🏠 LOCAL DISK"])
    st.divider()
    
    pulse = fetch_pulse(mode)
    if pulse:
        i = pulse.get("intelligence", {})
        m = pulse.get("market", {})
        st.caption(f"Heartbeat: {pulse.get('timestamp', 'N/A')}")
        
        st.markdown("### Decision Engine (Backtest)")
        st.metric("Danger Score", f"{i.get('danger_score', 0)}/4")
        st.metric("VIX Ceiling", f"{i.get('vix_threshold', 20.0):.1f}")
        
        st.divider()
        st.markdown("### Strategy Indicators")
        st.metric("Consensus", f"{i.get('consensus', 0)}/4 Match")
        st.caption(f"Bias: {i.get('bias', 'N/A')}")
    else:
        st.error("Backend Disconnected.")

# ─────────────────────────────────────────────────────────────────────────────
# 4. STRATEGIC RADAR (THE REPLICA)
# ─────────────────────────────────────────────────────────────────────────────

if pulse:
    st.title("🎯 SpreadGuard All-Tiers Radar")
    
    m = pulse.get("market", {})
    v1, v2, v3, v4, v5 = st.columns(5)
    v1.metric("NIFTY SPOT", f"{m.get('spot', 0):,.2f}")
    v2.metric("INDIA VIX", f"{m.get('vix', 0):.2f}")
    v3.metric("ATR (14d)", f"{m.get('atr', 0):.1f} pts")
    v4.metric("VELOCITY", f"{m.get('velocity', 0):.2f}%")
    v5.metric("5d ROC", f"{m.get('roc5', 0):.2f}%")
    
    st.divider()
    
    col_safe, col_agg = st.columns(2)
    tiers = pulse.get("tiers", [])
    
    with col_safe:
        st.subheader("🟢 HIGH CONVICTION TIERS")
        st.caption("Ultra-safe, lowest volatility regimes. Highly recommended.")
        
        for t in [x for x in tiers if x["safe"]]:
            status_cls = "status-active-safe" if t["active"] else "status-inactive"
            badge = "<span class='active-badge'>ACTIVE - GO</span>" if t["active"] else ""
            
            # Strike Logic
            strike_info = "Conditions not met"
            if t["active"]:
                base_spot = m.get("spot", 0)
                if t["type"] == "Bull Put":
                    strike = int(round((base_spot - t["otm"]) / 50) * 50)
                    strike_info = f"Sell {strike} PE"
            
            st.markdown(f"""
            <div class='tier-card {status_cls}'>
                <div class='tier-title'>{t['name']} {badge}</div>
                <div class='tier-meta' style='color: {"#00FF85" if t["active"] else "#4F565E"};'>{strike_info}</div>
            </div>
            """, unsafe_allow_html=True)

    with col_agg:
        st.subheader("🟡 AGGRESSIVE TIERS")
        st.caption("Higher frequency trading. Intraday drawdown possible, but expected to recover by close.")
        
        for t in [x for x in tiers if not x["safe"]]:
            status_cls = "status-active-danger" if t["active"] else "status-inactive"
            badge = "<span class='active-badge' style='background-color:#FFD700;color:#000;'>ACTIVE - GO</span>" if t["active"] else ""
            
            strike_info = "Conditions not met"
            if t["active"]:
                base_spot = m.get("spot", 0)
                if t["type"] == "Bull Put":
                    strike = int(round((base_spot - t["otm"]) / 50) * 50)
                    strike_info = f"Sell {strike} PE"
                elif t["type"] == "Iron Condor":
                    sp = int(round((base_spot - t["otm"]) / 50) * 50)
                    sc = int(round((base_spot + t["otm"]) / 50) * 50)
                    strike_info = f"Sell {sp} PE / {sc} CE"
                elif t["type"] == "Bear Call":
                    strike = int(round((base_spot + t["otm"]) / 50) * 50)
                    strike_info = f"Sell {strike} CE"
            
            st.markdown(f"""
            <div class='tier-card {status_cls}'>
                <div class='tier-title'>{t['name']} {badge}</div>
                <div class='tier-meta' style='color: {"#FFD700" if t["active"] else "#4F565E"};'>{strike_info}</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    
    # ─────────────────────────────────────────────────────────────────────────
    # 5. EXECUTION RULEBOOK (THE RESTORATION)
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown("### 📋 Execution Rulebook (Safe Tiers Only)")
    st.info("**Target Expiry:** 21 Apr (Tuesday)")
    st.success("**Entry:** 11:30 AM | **Hold:** 1-7 Days depending on Tier")
    
    st.markdown("""
    **Risk Protocol:**
    - **Max Layers:** Strict maximum 3 concurrent layers.
    - **TP:** Exit manually on decay, or hold to expiry if perfectly calm.
    - **Circuit Breaker:** Always honor a 3-day pause if a spread gets breached.
    """)

# ── AUTO REFRESH LOOP ──
time.sleep(15)
st.rerun()
