"""
StockWatch Pro — Real-time stock price monitor with WhatsApp alerts
Dependencies: streamlit, requests, pandas, whatsapp-api-client-python, qrcode, Pillow
"""

import streamlit as st
import requests
import time
import json
import io
import pandas as pd
from datetime import datetime
from pathlib import Path

# ── Optional WhatsApp imports (graceful if not installed) ─────────────────────
try:
    from whatsapp import WhatsApp
    WA_AVAILABLE = True
except ImportError:
    WA_AVAILABLE = False

try:
    import qrcode
    from PIL import Image
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="StockWatch Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Inter:wght@300;400;600&display=swap');
:root{--bg:#0a0e1a;--surface:#111827;--border:#1e2d40;--accent:#00d4ff;
      --green:#00ff88;--red:#ff4466;--yellow:#ffd700;--text:#e2e8f0;--muted:#64748b;}
html,body,[data-testid="stAppViewContainer"]{background:var(--bg)!important;
  color:var(--text)!important;font-family:'Inter',sans-serif;}
[data-testid="stSidebar"]{background:var(--surface)!important;border-right:1px solid var(--border);}
h1,h2,h3{font-family:'Space Mono',monospace;}
.metric-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:20px 24px;position:relative;overflow:hidden;transition:border-color 0.3s;}
.metric-card:hover{border-color:var(--accent);}
.metric-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,var(--accent),transparent);}
.metric-card.alert-card::before{background:linear-gradient(90deg,var(--red),var(--yellow));
  animation:pulse 1s ease-in-out infinite;}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
.ticker-symbol{font-family:'Space Mono',monospace;font-size:1.1rem;font-weight:700;
  color:var(--accent);letter-spacing:2px;}
.company-name{font-size:0.78rem;color:var(--muted);margin-bottom:12px;}
.price-big{font-family:'Space Mono',monospace;font-size:2rem;font-weight:700;line-height:1;}
.change-pos{color:var(--green);}.change-neg{color:var(--red);}.change-neutral{color:var(--muted);}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.7rem;
  font-family:'Space Mono',monospace;font-weight:700;}
.badge-alert{background:rgba(255,68,102,0.15);color:var(--red);border:1px solid var(--red);}
.badge-ok{background:rgba(0,255,136,0.10);color:var(--green);border:1px solid rgba(0,255,136,0.3);}
.header-band{background:linear-gradient(135deg,#0d1b2a 0%,#1a2744 100%);border:1px solid var(--border);
  border-radius:12px;padding:20px 30px;margin-bottom:24px;display:flex;align-items:center;gap:16px;}
.stButton>button{background:var(--accent)!important;color:#000!important;border:none!important;
  font-family:'Space Mono',monospace!important;font-weight:700!important;border-radius:6px!important;letter-spacing:1px;}
.stButton>button:hover{opacity:0.85!important;}
.alert-box{background:rgba(255,68,102,0.08);border:1px solid var(--red);border-radius:8px;
  padding:12px 16px;margin:8px 0;font-size:0.85rem;}
.divider{border-top:1px solid var(--border);margin:16px 0;}
.wa-connected{color:var(--green);font-family:'Space Mono',monospace;font-size:0.8rem;}
.wa-connecting{color:var(--yellow);font-family:'Space Mono',monospace;font-size:0.8rem;}
.wa-disconnected{color:var(--red);font-family:'Space Mono',monospace;font-size:0.8rem;}
.rec-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 16px;margin:4px 0;}
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
FINNHUB_KEY  = "d6c5mt1r01qsiik0ricgd6c5mt1r01qsiik0rid0"
FINNHUB_BASE = "https://finnhub.io/api/v1"
CONFIG_FILE  = Path("stockwatch_config.json")

DEFAULT_CONFIG = {
    "stocks": [
        {"symbol": "CSCO",  "name": "Cisco Systems",    "alert_pct": 2.0},
        {"symbol": "GSK",   "name": "GSK plc",           "alert_pct": 2.0},
        {"symbol": "GOOGL", "name": "Alphabet (Google)", "alert_pct": 2.0},
    ],
    "whatsapp": {
        "recipients":    [],
        "wa_session_id": "stockwatch",
    },
    "refresh_interval": 60,
}

# ── Config helpers ────────────────────────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                saved = json.load(f)
            return {
                "stocks":           saved.get("stocks",           DEFAULT_CONFIG["stocks"]),
                "whatsapp":         {**DEFAULT_CONFIG["whatsapp"], **saved.get("whatsapp", {})},
                "refresh_interval": saved.get("refresh_interval", 60),
            }
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def serialise_config(cfg: dict) -> dict:
    """Return a JSON-safe copy of config (strip runtime-only fields)."""
    return {
        "stocks": cfg["stocks"],
        "whatsapp": {
            "recipients":    cfg["whatsapp"]["recipients"],
            "wa_session_id": cfg["whatsapp"]["wa_session_id"],
        },
        "refresh_interval": cfg["refresh_interval"],
    }


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(serialise_config(cfg), f, indent=2)


# ── Session state bootstrap ───────────────────────────────────────────────────
if "config"        not in st.session_state: st.session_state.config        = load_config()
if "price_history" not in st.session_state: st.session_state.price_history = {}
if "alerts_sent"   not in st.session_state: st.session_state.alerts_sent   = {}
if "last_refresh"  not in st.session_state: st.session_state.last_refresh  = None
if "wa_client"     not in st.session_state: st.session_state.wa_client     = None
if "wa_qr_image"   not in st.session_state: st.session_state.wa_qr_image   = None
if "wa_connected"  not in st.session_state: st.session_state.wa_connected  = False
if "wa_connecting" not in st.session_state: st.session_state.wa_connecting = False
if "save_msg"      not in st.session_state: st.session_state.save_msg      = ""

cfg = st.session_state.config   # convenient alias

# ── Finnhub helpers ───────────────────────────────────────────────────────────
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


def pct_change(current: float, reference: float) -> float:
    return 0.0 if reference == 0 else ((current - reference) / reference) * 100


# ── Alert message ─────────────────────────────────────────────────────────────
def build_alert_message(alerts: list) -> str:
    lines = ["🚨 *StockWatch Pro Alert*\n"]
    for a in alerts:
        direction = "⬆️ UP" if a["change"] > 0 else "⬇️ DOWN"
        lines.append(
            f"*{a['symbol']}* ({a['name']})\n"
            f"Price: {a['currency']}{a['price']:.2f}  |  "
            f"Change: {direction} {abs(a['change']):.2f}%\n"
            f"Threshold: ±{a['threshold']:.1f}%"
        )
    lines.append(f"\n_Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC_")
    return "\n\n".join(lines)


# ── WhatsApp helpers ──────────────────────────────────────────────────────────
def send_whatsapp_alerts(message: str, recipients: list) -> list:
    results = []
    client = st.session_state.wa_client
    if not client or not st.session_state.wa_connected:
        return [("—", "—", False, "WhatsApp not connected")]
    for rec in recipients:
        phone = rec["phone"].replace("+", "").replace(" ", "").replace("-", "")
        try:
            client.send_message(phone, message)
            results.append((rec["name"], phone, True, ""))
        except Exception as e:
            results.append((rec["name"], phone, False, str(e)))
    return results


def init_wa_client(session_id: str):
    if not WA_AVAILABLE:
        st.error("whatsapp-api-client-python not installed.")
        return

    def on_qr(qr_data: str):
        if QR_AVAILABLE:
            img = qrcode.make(qr_data)
            st.session_state.wa_qr_image = img
        st.session_state.wa_connecting = True
        st.session_state.wa_connected  = False

    def on_ready():
        st.session_state.wa_connected  = True
        st.session_state.wa_connecting = False
        st.session_state.wa_qr_image   = None

    try:
        client = WhatsApp(session=session_id, on_qr=on_qr, on_ready=on_ready)
        st.session_state.wa_client    = client
        st.session_state.wa_connecting = True
    except Exception as e:
        st.error(f"WhatsApp init error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ── Config persistence ────────────────────────────────────────────────────
    st.markdown("### 💾 Config File")

    col_sv, col_rl = st.columns(2)
    with col_sv:
        if st.button("💾 Save", use_container_width=True):
            save_config(cfg)
            st.session_state.save_msg = f"Saved {datetime.now().strftime('%H:%M:%S')}"
    with col_rl:
        if st.button("📂 Reload", use_container_width=True):
            st.session_state.config = load_config()
            cfg = st.session_state.config
            st.session_state.save_msg = f"Reloaded {datetime.now().strftime('%H:%M:%S')}"
            st.rerun()

    if st.session_state.save_msg:
        st.caption(f"✅ {st.session_state.save_msg}")

    # Download JSON
    cfg_json = json.dumps(serialise_config(cfg), indent=2)
    st.download_button(
        "⬇️ Download config.json",
        data=cfg_json,
        file_name="stockwatch_config.json",
        mime="application/json",
        use_container_width=True,
    )

    # Upload JSON
    uploaded = st.file_uploader("⬆️ Upload config.json", type="json", label_visibility="collapsed")
    if uploaded:
        try:
            imp = json.load(uploaded)
            st.session_state.config = {
                "stocks":           imp.get("stocks",           DEFAULT_CONFIG["stocks"]),
                "whatsapp":         {**DEFAULT_CONFIG["whatsapp"], **imp.get("whatsapp", {})},
                "refresh_interval": imp.get("refresh_interval", 60),
            }
            cfg = st.session_state.config
            st.success("Config imported!")
            st.rerun()
        except Exception as e:
            st.error(f"Invalid file: {e}")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ── WhatsApp connection ───────────────────────────────────────────────────
    st.markdown("### 📱 WhatsApp")

    if st.session_state.wa_connected:
        st.markdown('<span class="wa-connected">● CONNECTED</span>', unsafe_allow_html=True)
    elif st.session_state.wa_connecting:
        st.markdown('<span class="wa-connecting">⏳ AWAITING QR SCAN…</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="wa-disconnected">● NOT CONNECTED</span>', unsafe_allow_html=True)

    session_id = st.text_input(
        "Session name",
        value=cfg["whatsapp"].get("wa_session_id", "stockwatch"),
        help="Reuse the same name to restore a previously-authorised session without re-scanning.",
    )
    cfg["whatsapp"]["wa_session_id"] = session_id

    cc, dc = st.columns(2)
    with cc:
        if st.button("🔗 Connect", use_container_width=True, disabled=st.session_state.wa_connected):
            init_wa_client(session_id)
            st.rerun()
    with dc:
        if st.button("✂️ Disconnect", use_container_width=True, disabled=not st.session_state.wa_connected):
            st.session_state.wa_client    = None
            st.session_state.wa_connected = False
            st.session_state.wa_connecting = False
            st.session_state.wa_qr_image  = None
            st.rerun()

    if not WA_AVAILABLE:
        st.warning("Install: `pip install whatsapp-api-client-python qrcode Pillow`")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ── Recipients ────────────────────────────────────────────────────────────
    st.markdown("### 👥 Alert Recipients")

    recipients = cfg["whatsapp"].setdefault("recipients", [])
    to_del_rec = []
    for ri, rec in enumerate(recipients):
        rc1, rc2 = st.columns([4, 1])
        with rc1:
            st.markdown(f"**{rec['name']}**  \n`{rec['phone']}`")
        with rc2:
            if st.button("✕", key=f"rdel_{ri}"):
                to_del_rec.append(ri)
    for i in sorted(to_del_rec, reverse=True):
        recipients.pop(i)
    if to_del_rec:
        st.rerun()

    with st.form("add_rec", clear_on_submit=True):
        rn = st.text_input("Name",  placeholder="e.g. Alice")
        rp = st.text_input("Phone (intl format)", placeholder="+447700900000")
        if st.form_submit_button("➕ Add Recipient"):
            if rn and rp:
                recipients.append({"name": rn.strip(), "phone": rp.strip()})
                st.rerun()
            else:
                st.error("Name and phone required.")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ── Refresh ───────────────────────────────────────────────────────────────
    st.markdown("### 🔄 Refresh")
    cfg["refresh_interval"] = st.selectbox(
        "Auto-refresh interval",
        options=[30, 60, 120, 300],
        index=[30, 60, 120, 300].index(int(cfg.get("refresh_interval", 60))),
        format_func=lambda x: f"{x} seconds",
    )
    auto_refresh = st.checkbox("Enable auto-refresh", value=False)
    if st.button("🔃 Refresh Now", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_refresh = datetime.now()
        st.rerun()

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ── Watchlist ─────────────────────────────────────────────────────────────
    st.markdown("### ➕ Add Stock")
    with st.form("add_stock", clear_on_submit=True):
        ns = st.text_input("Ticker",  placeholder="e.g. AAPL").upper().strip()
        nn = st.text_input("Name",    placeholder="e.g. Apple Inc.")
        na = st.number_input("Alert %", min_value=0.1, max_value=50.0, value=2.0, step=0.5)
        if st.form_submit_button("Add Stock"):
            if ns and nn:
                if ns not in [s["symbol"] for s in cfg["stocks"]]:
                    cfg["stocks"].append({"symbol": ns, "name": nn, "alert_pct": na})
                    st.rerun()
                else:
                    st.warning(f"{ns} already in list.")
            else:
                st.error("Ticker and name required.")

    st.markdown("### 📋 Watchlist")
    to_del_s = []
    for idx, stock in enumerate(cfg["stocks"]):
        sc1, sc2 = st.columns([3, 1])
        with sc1:
            new_pct = st.number_input(
                f"{stock['symbol']} alert %",
                min_value=0.1, max_value=50.0,
                value=float(stock["alert_pct"]),
                step=0.5, key=f"pct_{idx}",
            )
            cfg["stocks"][idx]["alert_pct"] = new_pct
        with sc2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("✕", key=f"sdel_{idx}"):
                to_del_s.append(idx)
    for i in sorted(to_del_s, reverse=True):
        cfg["stocks"].pop(i)
    if to_del_s:
        st.rerun()

    if st.button("↺ Reset to Defaults", use_container_width=True):
        st.session_state.config        = json.loads(json.dumps(DEFAULT_CONFIG))
        st.session_state.price_history = {}
        st.session_state.alerts_sent   = {}
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN PANEL
# ═══════════════════════════════════════════════════════════════════════════════

# Header
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

ts = st.session_state.last_refresh or datetime.now()
st.caption(f"Last data: {ts.strftime('%Y-%m-%d %H:%M:%S')} UTC  |  Finnhub free tier ~15 min delay")

# ── QR Code panel ─────────────────────────────────────────────────────────────
if st.session_state.wa_connecting and not st.session_state.wa_connected:
    st.markdown("---")
    qcol, icol = st.columns([1, 2])
    with qcol:
        st.markdown("### 📲 Scan to Connect")
        if st.session_state.wa_qr_image and QR_AVAILABLE:
            buf = io.BytesIO()
            st.session_state.wa_qr_image.save(buf, format="PNG")
            st.image(buf.getvalue(), caption="Scan with WhatsApp", width=220)
        else:
            st.info("QR code loading…\n\nEnsure `qrcode` and `Pillow` are installed.")
    with icol:
        st.markdown("### How to link your phone")
        st.markdown("""
1. Open **WhatsApp** on your phone
2. Tap **⋮** (Android) or **Settings** (iPhone)
3. Select **Linked Devices** → **Link a Device**
4. Point your camera at the QR code
5. The status above will show **● CONNECTED**

> The session is saved locally under the **session name** you set.
> On next startup, if you use the same name, you may not need to re-scan.
        """)
        if st.button("🔄 Refresh QR"):
            st.rerun()
    st.markdown("---")

# ── Fetch quotes ──────────────────────────────────────────────────────────────
quotes           = {}
alerts_triggered = []

for stock in cfg["stocks"]:
    sym = stock["symbol"]
    q   = get_quote(sym)
    quotes[sym] = q

    if "c" in q and q["c"] and q["c"] != 0:
        price      = q["c"]
        prev_close = q.get("pc", price)
        ref        = q.get("o") or prev_close or price
        change     = pct_change(price, ref)

        hist = st.session_state.price_history.setdefault(sym, [])
        if not hist or hist[-1] != price:
            hist.append(price)
            if len(hist) > 200:
                hist.pop(0)

        if abs(change) >= stock["alert_pct"]:
            last = st.session_state.alerts_sent.get(sym, 0)
            if time.time() - last > 600:
                st.session_state.alerts_sent[sym] = time.time()
                currency = "£" if sym.endswith(".L") else "$"
                alerts_triggered.append({
                    "symbol":    sym,
                    "name":      stock["name"],
                    "price":     price,
                    "change":    change,
                    "threshold": stock["alert_pct"],
                    "currency":  currency,
                })

# ── Alerts panel ──────────────────────────────────────────────────────────────
if alerts_triggered:
    st.markdown("---")
    st.markdown("### 🚨 Price Alerts")
    for a in alerts_triggered:
        direction = "⬆️ UP" if a["change"] > 0 else "⬇️ DOWN"
        st.markdown(
            f'<div class="alert-box"><b>{a["symbol"]}</b> — {a["name"]} is {direction} '
            f'<b>{abs(a["change"]):.2f}%</b> '
            f'(price: {a["currency"]}{a["price"]:.2f} | threshold ±{a["threshold"]:.1f}%)</div>',
            unsafe_allow_html=True,
        )

    alert_msg  = build_alert_message(alerts_triggered)
    recipients = cfg["whatsapp"].get("recipients", [])

    if recipients:
        if st.session_state.wa_connected and WA_AVAILABLE:
            if st.button("📲 Send WhatsApp Alerts to All Recipients", type="primary"):
                results = send_whatsapp_alerts(alert_msg, recipients)
                for name, phone, ok, err in results:
                    if ok:
                        st.success(f"✅ Sent to {name} ({phone})")
                    else:
                        st.error(f"❌ Failed — {name} ({phone}): {err}")
        else:
            st.warning("⚠️ WhatsApp not connected. Use the sidebar to connect and scan the QR code.")
    else:
        st.info("💡 Add recipients in the sidebar to enable WhatsApp alerts.")

    with st.expander("📋 Message preview"):
        st.code(alert_msg, language=None)
    st.markdown("---")

# ── Stock cards ───────────────────────────────────────────────────────────────
cols = st.columns(min(len(cfg["stocks"]), 3))

for idx, stock in enumerate(cfg["stocks"]):
    sym = stock["symbol"]
    q   = quotes.get(sym, {})
    with cols[idx % 3]:
        if "error" in q:
            st.error(f"❌ {sym}: {q['error']}")
            continue
        if not q or q.get("c", 0) == 0:
            st.warning(f"⚠️ {sym}: No data (market closed or invalid symbol)")
            continue

        price      = q["c"]
        prev_close = q.get("pc", price)
        day_open   = q.get("o",  prev_close)
        day_high   = q.get("h",  price)
        day_low    = q.get("l",  price)
        ref        = day_open or prev_close or price
        change_pct = pct_change(price, ref)
        change_abs = price - ref
        is_alert   = abs(change_pct) >= stock["alert_pct"]
        currency   = "£" if sym.endswith(".L") else "$"
        color_cls  = "change-pos" if change_pct > 0 else ("change-neg" if change_pct < 0 else "change-neutral")
        arrow      = "▲" if change_pct > 0 else ("▼" if change_pct < 0 else "—")
        badge      = ('<span class="badge badge-alert">⚡ ALERT</span>'
                      if is_alert else '<span class="badge badge-ok">✓ NORMAL</span>')

        st.markdown(
            f"""<div class="metric-card {'alert-card' if is_alert else ''}">
              <div class="ticker-symbol">{sym}</div>
              <div class="company-name">{stock['name']}</div>
              <div class="price-big {color_cls}">{currency}{price:,.3f}</div>
              <div style="margin-top:8px" class="{color_cls}">
                {arrow} {abs(change_abs):.3f} &nbsp;({abs(change_pct):.2f}%)
              </div>
              <hr style="border-color:#1e2d40;margin:12px 0"/>
              <div style="font-size:0.75rem;color:#64748b;font-family:'Space Mono',monospace">
                H: {currency}{day_high:,.3f} &nbsp;|&nbsp; L: {currency}{day_low:,.3f}<br>
                Prev close: {currency}{prev_close:,.3f}<br>
                Alert threshold: ±{stock['alert_pct']:.1f}%
              </div>
              <div style="margin-top:10px">{badge}</div>
            </div>""",
            unsafe_allow_html=True,
        )

# ── Recipients display ────────────────────────────────────────────────────────
recipients = cfg["whatsapp"].get("recipients", [])
if recipients:
    st.markdown("---")
    st.markdown("### 👥 Alert Recipients")
    rcols = st.columns(min(len(recipients), 4))
    for ri, rec in enumerate(recipients):
        with rcols[ri % 4]:
            st.markdown(
                f'<div class="rec-card"><b>{rec["name"]}</b><br>'
                f'<span style="font-family:Space Mono,monospace;font-size:0.75rem;color:#64748b">'
                f'{rec["phone"]}</span></div>',
                unsafe_allow_html=True,
            )

# ── Price history ─────────────────────────────────────────────────────────────
if any(st.session_state.price_history.values()):
    st.markdown("---")
    with st.expander("📊 In-session price history"):
        df_data = {}
        max_len = max(len(v) for v in st.session_state.price_history.values())
        for sym, hist in st.session_state.price_history.items():
            df_data[sym] = [None] * (max_len - len(hist)) + hist
        if df_data:
            df = pd.DataFrame(df_data)
            df.index = range(1, len(df) + 1)
            df.index.name = "Tick"
            st.line_chart(df)
            st.dataframe(df.tail(20).style.format(lambda x: f"{x:.3f}" if x is not None else "—"),
                         use_container_width=True)

# ── Debug / config viewer ─────────────────────────────────────────────────────
with st.expander("🛠️ Current config (JSON)"):
    st.json(serialise_config(cfg))

with st.expander("🔍 Raw Finnhub API response"):
    st.json(quotes)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(cfg["refresh_interval"])
    st.cache_data.clear()
    st.session_state.last_refresh = datetime.now()
    st.rerun()
