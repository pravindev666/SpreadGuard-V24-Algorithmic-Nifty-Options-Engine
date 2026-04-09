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
    
    .tier-card { background: #101418; border: 1px solid #1F2428; border-radius: 4px; padding: 12px; margin-bottom: 8px; min-height: 85px;}
    .status-active-safe { border-left: 4px solid #00FF85; }
    .status-active-danger { border-left: 4px solid #FFD700; }
    .status-inactive { border-left: 4px solid #2D3436; color: #4F565E; }
    
    .hud-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.85rem; }
    .hud-row { border-bottom: 1px solid #1F2428; }
    .hud-label { padding: 8px; color: #888; text-align: left; }
    .hud-value { padding: 8px; text-align: right; font-weight: bold; }
    
    .bull-text { color: #00FF85; }
    .bear-text { color: #FF4B2B; }
    .signal-box { padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: bold;}
    .strike-text { color: #FFF; font-weight: bold; font-size: 0.95rem; margin-top: 4px;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# 2. STATE LOADER
# ─────────────────────────────────────────────────────────────────────────────

RAW_URL = "https://raw.githubusercontent.com/pravindev666/SpreadGuard-V24-Algorithmic-Nifty-Options-Engine/main/data/intelligence_pulse_V2.json"

@st.cache_data(ttl=15)
def fetch_pulse(mode):
    if mode == "📡 LIVE CLOUD (GITHUB)":
        try:
            cache_buster = f"{RAW_URL}?t={int(time.time())}"
            response = requests.get(cache_buster)
            if response.status_code == 200: return response.json()
        except: pass
        return None
    else:
        path = "data/intelligence_pulse.json"
        if os.path.exists(path):
            with open(path, "r") as f: return json.load(f)
        return None

# ─────────────────────────────────────────────────────────────────────────────
# 3. SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🛡️ SENSOR HUB")
    mode = st.radio("Sync Source", ["📡 LIVE CLOUD (GITHUB)", "🏠 LOCAL DISK"])
    st.divider()
    
    pulse = fetch_pulse(mode)
    if pulse:
        i = pulse.get("intelligence", {})
        st.caption(f"Heartbeat: {pulse.get('timestamp', 'N/A')}")
        st.metric("Danger Score", f"{i.get('danger_score', 0)}/4")
        st.metric("VIX Ceiling", f"{i.get('vix_threshold', 22.0):.1f}")
        st.divider()
        st.metric("Trend Match", i.get("consensus", "0/4"))
        st.caption(f"Anchor: {i.get('anchor', 'N/A')}")
    else:
        st.error("Backend Disconnected.")

# ─────────────────────────────────────────────────────────────────────────────
# 4. STRATEGIC RADAR (FULL 12 TIERS + SPREAD HEDGING)
# ─────────────────────────────────────────────────────────────────────────────

if pulse:
    st.title("🎯 SpreadGuard All-Tiers Radar")
    
    m = pulse.get("market", {})
    i = pulse.get("intelligence", {})
    
    v1, v2, v3, v4, v5 = st.columns(5)
    v1.metric("NIFTY SPOT", f"{m.get('spot', 0):,.2f}")
    v2.metric("INDIA VIX", f"{m.get('vix', 0):.2f}")
    v3.metric("ATR (14d)", f"{m.get('atr', 0):.1f} pts")
    v4.metric("VELOCITY", f"{m.get('velocity', 0):.2f}%")
    v5.metric("VIX DIV.", f"{m.get('vix_div', 'STABLE')}")
    
    st.divider()
    
    col_safe, col_agg = st.columns(2)
    tiers = pulse.get("tiers", [])
    
    with col_safe:
        st.subheader("🟢 HIGH CONVICTION TIERS")
        for t in [x for x in tiers if x["safe"]]:
            status_cls = "status-active-safe" if t["active"] else "status-inactive"
            strike_info = "Conditions not met"
            if t["active"]:
                base_spot = m.get("spot", 0)
                otm = t.get("otm", 500)
                hedge = t.get("hedge", 200)
                
                if t["type"] == "Bull Put":
                    sell_k = int(round((base_spot - otm) / 50) * 50)
                    buy_k = sell_k - hedge
                    strike_info = f"Sell {sell_k} PE | Buy {buy_k} PE"
                elif t["type"] == "Iron Fly":
                    atm_k = int(round(base_spot / 50) * 50)
                    strike_info = f"Sell {atm_k} PC | Buy Wings"

            st.markdown(f"""
            <div class='tier-card {status_cls}'>
                <div class='tier-title'>{t['name']} {"<span class='signal-box' style='background:#00FF85;color:#000'>ACTIVE</span>" if t['active'] else ""}</div>
                <div class='strike-text' style='color: {"#FFF" if t["active"] else "#4F565E"}'>{strike_info}</div>
            </div>
            """, unsafe_allow_html=True)

    with col_agg:
        st.subheader("🟡 AGGRESSIVE TIERS")
        for t in [x for x in tiers if not x["safe"]]:
            status_cls = "status-active-danger" if t["active"] else "status-inactive"
            strike_info = "Conditions not met"
            if t["active"]:
                base_spot = m.get("spot", 0)
                otm = t.get("otm", 400)
                hedge = t.get("hedge", 500)
                
                if t["type"] == "Bull Put":
                    sell_k = int(round((base_spot - otm) / 50) * 50)
                    buy_k = sell_k - hedge
                    strike_info = f"Sell {sell_k} PE | Buy {buy_k} PE"
                elif t["type"] == "Iron Condor":
                    sp = int(round((base_spot - otm) / 50) * 50)
                    sc = int(round((base_spot + otm) / 50) * 50)
                    strike_info = f"Sell {sp} PE | {sc} CE"
                elif t["type"] == "Bear Call":
                    sell_k = int(round((base_spot + otm) / 50) * 50)
                    buy_k = sell_k + hedge
                    strike_info = f"Sell {sell_k} CE | Buy {buy_k} CE"

            st.markdown(f"""
            <div class='tier-card {status_cls}'>
                <div class='tier-title'>{t['name']} {"<span class='signal-box' style='background:#FFD700;color:#000'>ACTIVE</span>" if t['active'] else ""}</div>
                <div class='strike-text' style='color: {"#FFF" if t["active"] else "#4F565E"}'>{strike_info}</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    
    # ─────────────────────────────────────────────────────────────────────────
    # 5. DEEP AWARENESS HUD
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown("### 🛡️ SpreadGuard Elite Awareness HUD")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Environment Pulse**")
        mode = i.get("mode", "NORMAL"); status = i.get("status", "STABLE")
        mtf = i.get("mtf", "CONFLICT"); vix_div = m.get("vix_div", "STABLE")
        velocity = m.get("velocity", 0.0); v_veto = i.get("vwap_veto", False)
        st.markdown(f"""<table class='hud-table'>
            <tr class='hud-row'><td class='hud-label'>MODE</td><td class='hud-value' style='color: {"#FF4B2B" if mode=="LOCKDOWN" else "#FFF"}'>{mode}</td></tr>
            <tr class='hud-row'><td class='hud-label'>STATUS</td><td class='hud-value' style='color: {"#FFD700" if "STORM" in status else "#FFF"}'>{status}</td></tr>
            <tr class='hud-row'><td class='hud-label'>VIX DIV.</td><td class='hud-value' style='color: {"#FF4B2B" if "DIVERGENT" in vix_div else "#00FF85"}'>{vix_div}</td></tr>
            <tr class='hud-row'><td class='hud-label'>V24 VELOCITY</td><td class='hud-value' style='color: {"#FF4B2B" if velocity > 4.0 else "#00FF85"}'>{velocity:.2f}%</td></tr>
            <tr class='hud-row'><td class='hud-label'>ANCHOR</td><td class='hud-value' style='color: #4A90E2;'>{i.get("anchor", "NEUTRAL")}</td></tr>
            <tr class='hud-row'><td class='hud-label'>MTF-TREND</td><td class='hud-value' style='color: {"#00FF85" if "UP" in mtf else "#FF4B2B"}'>{mtf}</td></tr>
            <tr class='hud-row'><td class='hud-label'>VWAP POS</td><td class='hud-value' style='color: {"#FF4B2B" if v_veto else "#00FF85"}'>{"BELOW (Bear)" if v_veto else "ABOVE (Bull)"}</td></tr>
        </table>""", unsafe_allow_html=True)
    with c2:
        st.markdown("**Sensor Pulse**")
        s = i.get("sensors", {})
        st.markdown(f"""<table class='hud-table'>
            <tr class='hud-row'><td class='hud-label'>EMA 20/50</td><td class='hud-value {"bull-text" if s.get("ema")=="BULL" else "bear-text"}'>{s.get("ema")}</td></tr>
            <tr class='hud-row'><td class='hud-label'>DMI (14)</td><td class='hud-value {"bull-text" if s.get("dmi")=="BULL" else "bear-text"}'>{s.get("dmi")}</td></tr>
            <tr class='hud-row'><td class='hud-label'>SuperTrend</td><td class='hud-value {"bull-text" if s.get("st")=="BULL" else "bear-text"}'>{s.get("st")}</td></tr>
            <tr class='hud-row'><td class='hud-label'>MACD SIG</td><td class='hud-value {"bull-text" if s.get("macd")=="BULL" else "bear-text"}'>{s.get("macd")}</td></tr>
        </table>""", unsafe_allow_html=True)

    st.divider()
    st.markdown("### 📋 Execution Rulebook (1:1 Master Protocol)")
    st.markdown("**Target Expiry:** 21 Apr (Tuesday)")
    st.markdown("**Entry:** 11:30 AM | **Hold:** 1-7 Days depending on Tier")
    st.markdown("""**Risk Protocol:**
    - **Max Layers:** Strict maximum 3 concurrent layers.
    - **TP:** Exit manually on decay, or hold to expiry if perfectly calm.
    - **Circuit Breaker:** Always honor a 3-day pause if a spread gets breached.""")

# ── AUTO REFRESH LOOP ──
time.sleep(15)
st.rerun()
