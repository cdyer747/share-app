import streamlit as st
import requests
import time
import json
import pandas as pd
from datetime import datetime
import urllib.parse

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="StockWatch Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Inter:wght@300;400;600&display=swap');

:root {
    --bg:       #0a0e1a;
    --surface:  #111827;
    --border:   #1e2d40;
    --accent:   #00d4ff;
    --green:    #00ff88;
    --red:      #ff4466;
    --yellow:   #ffd700;
    --text:     #e2e8f0;
    --muted:    #64748b;
}

html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Inter', sans-serif;
}

[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border);
}

h1, h2, h3 { font-family: 'Space Mono', monospace; }

.metric-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 24px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.3s;
}
.metric-card:hover { border-color: var(--accent); }
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent), transparent);
}
.metric-card.alert-card::before {
    background: linear-gradient(90deg, var(--red), var(--yellow));
    animation: pulse 1s ease-in-out infinite;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

.ticker-symbol {
    font-family: 'Space Mono', monospace;
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: 2px;
}
.company-name { font-size: 0.78rem; color: var(--muted); margin-bottom: 12px; }
.price-big {
    font-family: 'Space Mono', monospace;
    font-size: 2rem;
    font-weight: 700;
    line-height: 1;
}
.change-pos { color: var(--green); }
.change-neg { color: var(--red); }
.change-neutral { color: var(--muted); }
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.7rem;
    font-family: 'Space Mono', monospace;
    font-weight: 700;
}
.badge-alert { background: rgba(255,68,102,0.15); color: var(--red); border: 1px solid var(--red); }
.badge-ok    { background: rgba(0,255,136,0.10); color: var(--green); border: 1px solid rgba(0,255,136,0.3); }

.header-band {
    background: linear-gradient(135deg, #0d1b2a 0%, #1a2744 100%);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 30px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 16px;
}
.stButton > button {
    background: var(--accent) !important;
    color: #000 !important;
    border: none !important;
    font-family: 'Space Mono', monospace !important;
    font-weight: 700 !important;
    border-radius: 6px !important;
    letter-spacing: 1px;
}
.stButton > button:hover { opacity: 0.85 !important; }

[data-testid="stMetricValue"] { font-family: 'Space Mono', monospace !important; }
.whatsapp-btn {
    display: inline-block;
    background: #25D366;
    color: white !important;
    padding: 8px 18px;
    border-radius: 8px;
    font-family: 'Space Mono', monospace;
    font-size: 0.8rem;
    font-weight: 700;
    text-decoration: none;
    letter-spacing: 1px;
}
.alert-box {
    background: rgba(255,68,102,0.08);
    border: 1px solid var(--red);
    border-radius: 8px;
    padding: 12px 16px;
    margin: 8px 0;
    font-size: 0.85rem;
}
.divider { border-top: 1px solid var(--border); margin: 16px 0; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
FINNHUB_KEY = "d6c5mt1r01qsiik0ricgd6c5mt1r01qsiik0rid0"
FINNHUB_BASE = "https://finnhub.io/api/v1"

DEFAULT_STOCKS = [
    {"symbol": "CSCO",  "name": "Cisco Systems",     "alert_pct": 2.0},
    {"symbol": "GSK",   "name": "GSK plc",            "alert_pct": 2.0},
    {"symbol": "BT-A","name": "BT Group plc",       "alert_pct": 2.0},
]

# ── Session state ─────────────────────────────────────────────────────────────
if "stocks" not in st.session_state:
    st.session_state.stocks = DEFAULT_STOCKS.copy()
if "price_history" not in st.session_state:
    st.session_state.price_history = {}   # symbol -> list of prices
if "alerts_sent" not in st.session_state:
    st.session_state.alerts_sent = {}     # symbol -> last alert time
if "whatsapp_number" not in st.session_state:
    st.session_state.whatsapp_number = ""
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None

# ── Helpers ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def get_quote(symbol: str) -> dict:
    try:
        r = requests.get(
            f"{FINNHUB_BASE}/quote",
            params={"symbol": symbol, "token": FINNHUB_KEY},
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


@st.cache_data(ttl=3600)
def search_symbol(query: str) -> list:
    try:
        r = requests.get(
            f"{FINNHUB_BASE}/search",
            params={"q": query, "token": FINNHUB_KEY},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("result", [])[:10]
    except Exception:
        return []


def pct_change(current: float, reference: float) -> float:
    if reference == 0:
        return 0.0
    return ((current - reference) / reference) * 100


def make_whatsapp_link(phone: str, message: str) -> str:
    clean = phone.replace("+", "").replace(" ", "").replace("-", "")
    encoded = urllib.parse.quote(message)
    return f"https://wa.me/{clean}?text={encoded}"


def build_alert_message(alerts: list) -> str:
    lines = ["🚨 *StockWatch Alert*\n"]
    for a in alerts:
        direction = "⬆️ UP" if a["change"] > 0 else "⬇️ DOWN"
        lines.append(
            f"*{a['symbol']}* ({a['name']})\n"
            f"Price: {a['currency']}{a['price']:.2f} | "
            f"Change: {direction} {abs(a['change']):.2f}%\n"
            f"Threshold: ±{a['threshold']:.1f}%"
        )
    lines.append(f"\n_Alert time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")
    return "\n\n".join(lines)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # WhatsApp number
    st.markdown("### 📱 WhatsApp Alerts")
    wa_num = st.text_input(
        "Phone number (intl format)",
        value=st.session_state.whatsapp_number,
        placeholder="+447700900000",
        help="Include country code, e.g. +447700900000",
    )
    st.session_state.whatsapp_number = wa_num
    st.caption("WhatsApp Web link opens automatically when threshold is breached.")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # Refresh interval
    st.markdown("### 🔄 Refresh")
    auto_refresh = st.checkbox("Auto-refresh (every 60 s)", value=False)
    if st.button("🔃  Refresh Now", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_refresh = datetime.now()
        st.rerun()

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # Add stock
    st.markdown("### ➕ Add Stock")
    new_symbol = st.text_input("Ticker symbol", placeholder="e.g. AAPL").upper().strip()
    new_name   = st.text_input("Display name",  placeholder="e.g. Apple Inc.")
    new_alert  = st.number_input("Alert threshold (%)", min_value=0.1, max_value=50.0, value=2.0, step=0.5)

    if st.button("Add Stock", use_container_width=True):
        if new_symbol and new_name:
            existing = [s["symbol"] for s in st.session_state.stocks]
            if new_symbol not in existing:
                st.session_state.stocks.append(
                    {"symbol": new_symbol, "name": new_name, "alert_pct": new_alert}
                )
                st.success(f"Added {new_symbol}")
                st.rerun()
            else:
                st.warning(f"{new_symbol} already in watchlist.")
        else:
            st.error("Provide both symbol and name.")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # Manage existing stocks
    st.markdown("### 📋 Watchlist")
    to_remove = []
    for idx, stock in enumerate(st.session_state.stocks):
        col1, col2 = st.columns([3, 1])
        with col1:
            new_pct = st.number_input(
                f"{stock['symbol']} alert %",
                min_value=0.1, max_value=50.0,
                value=float(stock["alert_pct"]),
                step=0.5,
                key=f"pct_{idx}",
            )
            st.session_state.stocks[idx]["alert_pct"] = new_pct
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("✕", key=f"del_{idx}"):
                to_remove.append(idx)

    for i in sorted(to_remove, reverse=True):
        st.session_state.stocks.pop(i)
    if to_remove:
        st.rerun()

    # Reset to defaults
    if st.button("↺  Reset to Defaults", use_container_width=True):
        st.session_state.stocks = DEFAULT_STOCKS.copy()
        st.session_state.price_history = {}
        st.session_state.alerts_sent = {}
        st.rerun()


# ── Main header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="header-band">
  <span style="font-size:2.2rem">📈</span>
  <div>
    <h1 style="margin:0;font-size:1.8rem;color:#00d4ff">STOCKWATCH PRO</h1>
    <span style="color:#64748b;font-size:0.8rem;font-family:'Space Mono',monospace">
      REAL-TIME PRICE MONITOR · FINNHUB · WHATSAPP ALERTS
    </span>
  </div>
</div>
""", unsafe_allow_html=True)

# last refresh info
ts = st.session_state.last_refresh or datetime.now()
st.caption(f"Last data fetch: {ts.strftime('%Y-%m-%d %H:%M:%S')} UTC  |  Data delayed ~15 min for free tier.")

# ── Fetch prices & detect alerts ──────────────────────────────────────────────
quotes = {}
alerts_triggered = []

for stock in st.session_state.stocks:
    sym = stock["symbol"]
    q = get_quote(sym)
    quotes[sym] = q

    if "c" in q and q["c"] and q["c"] != 0:
        price = q["c"]
        prev_close = q.get("pc", price)

        # track history
        hist = st.session_state.price_history.setdefault(sym, [])
        if not hist or hist[-1] != price:
            hist.append(price)
            if len(hist) > 200:
                hist.pop(0)

        # calculate change from day open (or prev close if open missing)
        ref = q.get("o") or prev_close or price
        change = pct_change(price, ref)

        if abs(change) >= stock["alert_pct"]:
            # only fire once every 10 minutes per symbol
            last = st.session_state.alerts_sent.get(sym, 0)
            if time.time() - last > 600:
                st.session_state.alerts_sent[sym] = time.time()
                currency = "£" if sym.endswith(".L") else "$"
                alerts_triggered.append({
                    "symbol": sym,
                    "name": stock["name"],
                    "price": price,
                    "change": change,
                    "threshold": stock["alert_pct"],
                    "currency": currency,
                })

# ── Alert banner + WhatsApp button ───────────────────────────────────────────
if alerts_triggered:
    st.markdown("---")
    st.markdown("### 🚨 Price Alerts Triggered")
    for a in alerts_triggered:
        direction = "⬆️ UP" if a["change"] > 0 else "⬇️ DOWN"
        st.markdown(
            f'<div class="alert-box">'
            f'<b>{a["symbol"]}</b> — {a["name"]} is {direction} '
            f'<b>{abs(a["change"]):.2f}%</b> '
            f'(current: {a["currency"]}{a["price"]:.2f} | threshold: ±{a["threshold"]:.1f}%)'
            f'</div>',
            unsafe_allow_html=True,
        )

    msg = build_alert_message(alerts_triggered)
    if st.session_state.whatsapp_number:
        wa_link = make_whatsapp_link(st.session_state.whatsapp_number, msg)
        st.markdown(
            f'<a class="whatsapp-btn" href="{wa_link}" target="_blank">📲  Send via WhatsApp</a>',
            unsafe_allow_html=True,
        )
        st.caption("Click to open WhatsApp Web pre-filled with the alert message.")
    else:
        st.info("💡 Enter your WhatsApp number in the sidebar to enable one-click alert sending.")

    # show raw message for copy-paste
    with st.expander("📋 Alert message preview"):
        st.code(msg, language=None)
    st.markdown("---")

# ── Stock cards ───────────────────────────────────────────────────────────────
cols = st.columns(min(len(st.session_state.stocks), 3))

for idx, stock in enumerate(st.session_state.stocks):
    sym = stock["symbol"]
    q   = quotes.get(sym, {})
    col = cols[idx % 3]

    with col:
        if "error" in q:
            st.error(f"❌ {sym}: {q['error']}")
            continue
        if not q or q.get("c", 0) == 0:
            st.warning(f"⚠️ {sym}: No data (market may be closed or symbol invalid)")
            continue

        price      = q["c"]
        prev_close = q.get("pc", price)
        day_open   = q.get("o", prev_close)
        day_high   = q.get("h", price)
        day_low    = q.get("l", price)
        ref        = day_open or prev_close or price
        change_pct = pct_change(price, ref)
        change_abs = price - ref

        is_alert   = abs(change_pct) >= stock["alert_pct"]
        currency   = "£" if sym.endswith(".L") else "$"

        color_cls = "change-pos" if change_pct > 0 else ("change-neg" if change_pct < 0 else "change-neutral")
        arrow     = "▲" if change_pct > 0 else ("▼" if change_pct < 0 else "—")
        badge     = '<span class="badge badge-alert">⚡ ALERT</span>' if is_alert else '<span class="badge badge-ok">✓ NORMAL</span>'

        st.markdown(
            f"""
            <div class="metric-card {'alert-card' if is_alert else ''}">
              <div class="ticker-symbol">{sym}</div>
              <div class="company-name">{stock['name']}</div>
              <div class="price-big {color_cls}">{currency}{price:,.3f}</div>
              <div style="margin-top:8px" class="{color_cls}">
                {arrow} {abs(change_abs):.3f} ({abs(change_pct):.2f}%)
              </div>
              <hr style="border-color:#1e2d40;margin:12px 0"/>
              <div style="font-size:0.75rem;color:#64748b;font-family:'Space Mono',monospace">
                H: {currency}{day_high:,.3f} &nbsp;|&nbsp; L: {currency}{day_low:,.3f}<br>
                Prev close: {currency}{prev_close:,.3f}<br>
                Alert threshold: ±{stock['alert_pct']:.1f}%
              </div>
              <div style="margin-top:10px">{badge}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ── Price history table ───────────────────────────────────────────────────────
if any(st.session_state.price_history.values()):
    st.markdown("---")
    with st.expander("📊 In-session price history"):
        df_data = {}
        max_len = max(len(v) for v in st.session_state.price_history.values()) if st.session_state.price_history else 0
        for sym, hist in st.session_state.price_history.items():
            padded = [None] * (max_len - len(hist)) + hist
            df_data[sym] = padded

        if df_data:
            df = pd.DataFrame(df_data)
            df.index = range(1, len(df) + 1)
            df.index.name = "Tick"
            st.line_chart(df)
            st.dataframe(df.tail(20).style.format("{:.3f}"), use_container_width=True)

# ── All Quotes Raw Debug ──────────────────────────────────────────────────────
with st.expander("🔍 Raw API response (debug)"):
    st.json(quotes)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(60)
    st.cache_data.clear()
    st.session_state.last_refresh = datetime.now()
    st.rerun()
