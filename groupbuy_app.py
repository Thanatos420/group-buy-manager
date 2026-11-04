#!/usr/bin/env python3
"""
Group Buy Manager
Clean, simple tool for bulk purchase tracking
"""

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path(__file__).parent / "groupbuy.db"
DEFAULT_WHOLESALE = 335.0
DEFAULT_SELL = 500.0

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS buyers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        contact TEXT,
        status TEXT DEFAULT 'Prospect',
        typical_lbs REAL DEFAULT 1.0,
        last_cycle_date TEXT,
        total_cycles INTEGER DEFAULT 0,
        referred_by TEXT,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        status TEXT DEFAULT 'Open',
        opened_date TEXT,
        closed_date TEXT,
        wholesale_price REAL,
        sell_price REAL,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS commitments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cycle_id INTEGER,
        buyer_id INTEGER,
        lbs REAL,
        amount_due REAL,
        amount_paid REAL DEFAULT 0,
        payment_status TEXT DEFAULT 'Pending',
        notes TEXT,
        FOREIGN KEY (cycle_id) REFERENCES cycles(id),
        FOREIGN KEY (buyer_id) REFERENCES buyers(id)
    )""")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wholesale_price', ?)", (str(DEFAULT_WHOLESALE),))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sell_price', ?)", (str(DEFAULT_SELL),))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('reinvestment_fund', '0')")
    conn.commit()
    conn.close()

def get_setting(key, default=""):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def month_drop_name(d=None):
    d = d or date.today()
    return d.strftime("%b Drop")

# Page config
st.set_page_config(
    page_title="Group Buy",
    page_icon="📦",
    layout="centered",
    initial_sidebar_state="collapsed"
)

init_db()

# Custom CSS for cleaner, more native feel
st.markdown("""
<style>
    .stApp { max-width: 680px; margin: 0 auto; }
    .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
    h1 { font-size: 1.6rem !important; font-weight: 700 !important; letter-spacing: -0.3px; }
    h2, h3 { font-weight: 600 !important; }
    div[data-testid="stMetric"] {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 12px;
        padding: 12px 16px;
    }
    .stButton > button {
        border-radius: 10px;
        font-weight: 500;
    }
    .stSelectbox, .stTextInput, .stNumberInput {
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Navigation
pages = ["Home", "Buyers", "Cycles", "Active Drop", "Money", "Messages", "Settings"]
page = st.radio("", pages, horizontal=True, label_visibility="collapsed")

wholesale = float(get_setting("wholesale_price", DEFAULT_WHOLESALE))
sell = float(get_setting("sell_price", DEFAULT_SELL))

# ─── HOME ───────────────────────────────────────────────────
if page == "Home":
    st.title("Group Buy")
    st.caption("Track drops • buyers • profit")

    conn = get_conn()
    active = conn.execute("SELECT COUNT(*) FROM buyers WHERE status = 'Active'").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM buyers").fetchone()[0]
    open_cycle = conn.execute(
        "SELECT * FROM cycles WHERE status IN ('Open','Collecting','Ordered','Received') ORDER BY id DESC LIMIT 1"
    ).fetchone()
    profit = conn.execute("""
        SELECT COALESCE(SUM(c.amount_paid - (c.lbs * cy.wholesale_price)), 0)
        FROM commitments c JOIN cycles cy ON c.cycle_id = cy.id
        WHERE c.payment_status = 'Paid' AND cy.status = 'Closed'
    """).fetchone()[0]
    fund = float(get_setting("reinvestment_fund", "0"))

    c1, c2 = st.columns(2)
    c1.metric("Active Buyers", active)
    c2.metric("Total Buyers", total)
    c3, c4 = st.columns(2)
    c3.metric("Closed Profit", f"${profit:,.0f}")
    c4.metric("Reinvest Fund", f"${fund:,.0f}")

    st.divider()

    if open_cycle:
        name = open_cycle["name"] or f"Drop #{open_cycle['id']}"
        st.subheader(name)
        st.caption(f"Status: {open_cycle['status']}  ·  Opened {open_cycle['opened_date'] or '—'}")
        stats = conn.execute("""
            SELECT COALESCE(SUM(lbs),0) as lbs,
                   COALESCE(SUM(amount_due),0) as due,
                   COALESCE(SUM(amount_paid),0) as paid,
                   COUNT(*) as people
            FROM commitments WHERE cycle_id = ?
        """, (open_cycle["id"],)).fetchone()
        a, b, c = st.columns(3)
        a.metric("People", stats["people"])
        b.metric("lbs", f"{stats['lbs']:.2f}")
        c.metric("Collected", f"${stats['paid']:,.0f}")
        if stats["due"] > 0:
            st.progress(min(stats["paid"] / stats["due"], 1.0))
            st.caption(f"${stats['due'] - stats['paid']:,.0f} still due")
    else:
        st.info("No active drop. Go to **Cycles** to start one.")
    conn.close()

# ─── BUYERS ─────────────────────────────────────────────────
elif page == "Buyers":
    st.title("Buyers")

    tab1, tab2, tab3 = st.tabs(["List", "Add", "Remove"])

    with tab1:
        conn = get_conn()
        df = pd.read_sql_query(
            "SELECT id, name, status, typical_lbs, total_cycles, contact, referred_by FROM buyers ORDER BY status, name",
            conn
        )
        if df.empty:
            st.write("No buyers yet.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
        conn.close()

    with tab2:
        with st.form("add_buyer", clear_on_submit=True):
            name = st.text_input("Name")
            contact = st.text_input("Contact")
            status = st.selectbox("Status", ["Prospect", "New", "Active", "Occasional", "Inactive"])
            typical = st.number_input("Typical lbs", min_value=0.25, value=1.0, step=0.25)
            referred = st.text_input("Referred by")
            notes = st.text_area("Notes", height=80)
            if st.form_submit_button("Add Buyer", use_container_width=True):
                if name.strip():
                    conn = get_conn()
                    conn.execute(
                        "INSERT INTO buyers (name, contact, status, typical_lbs, referred_by, notes) VALUES (?,?,?,?,?,?)",
                        (name.strip(), contact, status, typical, referred, notes)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"Added {name}")
                    st.rerun()
                else:
                    st.error("Name required")

    with tab3:
        conn = get_conn()
        buyers = conn.execute("SELECT id, name, status FROM buyers ORDER BY name").fetchall()
        if not buyers:
            st.write("Nothing to remove.")
        else:
            options = {f"{b['name']} ({b['status']})": b["id"] for b in buyers}
            to_delete = st.selectbox("Select buyer to remove", list(options.keys()))
            if st.button("Remove Buyer", type="primary", use_container_width=True):
                bid = options[to_delete]
                conn.execute("DELETE FROM commitments WHERE buyer_id = ?", (bid,))
                conn.execute("DELETE FROM buyers WHERE id = ?", (bid,))
                conn.commit()
                st.success("Removed")
                st.rerun()
        conn.close()

# ─── CYCLES ─────────────────────────────────────────────────
elif page == "Cycles":
    st.title("Cycles")

    default_name = month_drop_name()

    with st.expander("Start New Drop", expanded=True):
        with st.form("new_cycle"):
            cname = st.text_input("Drop name", value=default_name)
            opened = st.date_input("Date", value=date.today())
            col1, col2 = st.columns(2)
            with col1:
                wh = st.number_input("Wholesale $/lb", value=wholesale, step=1.0)
            with col2:
                se = st.number_input("Sell $/lb", value=sell, step=1.0)
            notes = st.text_input("Notes (optional)")
            if st.form_submit_button("Create Drop", use_container_width=True):
                conn = get_conn()
                conn.execute(
                    "INSERT INTO cycles (name, status, opened_date, wholesale_price, sell_price, notes) VALUES (?,?,?,?,?,?)",
                    (cname or default_name, "Open", opened.isoformat(), wh, se, notes)
                )
                conn.commit()
                conn.close()
                st.success(f"Created {cname or default_name}")
                st.rerun()

    st.subheader("All Drops")
    conn = get_conn()
    cycles = pd.read_sql_query(
        "SELECT id, name, status, opened_date, wholesale_price, sell_price FROM cycles ORDER BY id DESC",
        conn
    )
    if cycles.empty:
        st.write("No drops yet.")
    else:
        st.dataframe(cycles, use_container_width=True, hide_index=True)

        st.markdown("#### Change Status")
        opts = {f"#{r['id']} {r['name']} ({r['status']})": r["id"] for _, r in cycles.iterrows()}
        sel = st.selectbox("Drop", list(opts.keys()))
        new_status = st.selectbox("New status", ["Open", "Collecting", "Ordered", "Received", "Distributed", "Closed"])
        if st.button("Update Status", use_container_width=True):
            cid = opts[sel]
            if new_status == "Closed":
                conn.execute("UPDATE cycles SET status=?, closed_date=? WHERE id=?", (new_status, date.today().isoformat(), cid))
            else:
                conn.execute("UPDATE cycles SET status=? WHERE id=?", (new_status, cid))
            conn.commit()
            st.success("Updated")
            st.rerun()
    conn.close()

# ─── ACTIVE DROP ────────────────────────────────────────────
elif page == "Active Drop":
    st.title("Active Drop")

    conn = get_conn()
    cycles = conn.execute("SELECT id, name, status, wholesale_price, sell_price FROM cycles ORDER BY id DESC").fetchall()
    if not cycles:
        st.warning("Create a drop first in Cycles.")
        st.stop()

    opts = {f"{c['name'] or 'Drop'} (#{c['id']}) — {c['status']}": c for c in cycles}
    label = st.selectbox("Select drop", list(opts.keys()))
    cycle = opts[label]
    cid = cycle["id"]

    st.caption(f"${cycle['wholesale_price']:.0f} wholesale  ·  ${cycle['sell_price']:.0f} sell")

    stats = conn.execute("""
        SELECT COALESCE(SUM(lbs),0) as lbs, COALESCE(SUM(amount_due),0) as due,
               COALESCE(SUM(amount_paid),0) as paid, COUNT(*) as people
        FROM commitments WHERE cycle_id = ?
    """, (cid,)).fetchone()

    a, b, c, d = st.columns(4)
    a.metric("People", stats["people"])
    b.metric("lbs", f"{stats['lbs']:.2f}")
    c.metric("In", f"${stats['paid']:,.0f}")
    d.metric("Due", f"${stats['due']-stats['paid']:,.0f}")

    st.divider()

    with st.expander("Add person to this drop", expanded=True):
        buyers = conn.execute("SELECT id, name, typical_lbs FROM buyers ORDER BY name").fetchall()
        if not buyers:
            st.write("Add buyers first.")
        else:
            bopts = {f"{b['name']} (~{b['typical_lbs']} lb)": b for b in buyers}
            with st.form("add_commit"):
                bsel = st.selectbox("Buyer", list(bopts.keys()))
                lbs = st.number_input("lbs", min_value=0.25, value=float(bopts[bsel]["typical_lbs"] or 1.0), step=0.25)
                amount = round(lbs * cycle["sell_price"], 2)
                st.write(f"Amount due: **${amount:.2f}**")
                paid = st.number_input("Already paid", min_value=0.0, value=0.0, step=25.0)
                pstatus = st.selectbox("Status", ["Pending", "Partial", "Paid"])
                if st.form_submit_button("Add", use_container_width=True):
                    buyer = bopts[bsel]
                    conn.execute(
                        "INSERT INTO commitments (cycle_id, buyer_id, lbs, amount_due, amount_paid, payment_status) VALUES (?,?,?,?,?,?)",
                        (cid, buyer["id"], lbs, amount, paid, pstatus)
                    )
                    conn.commit()
                    st.success("Added")
                    st.rerun()

    commits = pd.read_sql_query("""
        SELECT cm.id, b.name, cm.lbs, cm.amount_due, cm.amount_paid, cm.payment_status
        FROM commitments cm JOIN buyers b ON cm.buyer_id = b.id
        WHERE cm.cycle_id = ? ORDER BY b.name
    """, conn, params=(cid,))

    if not commits.empty:
        st.subheader("Commitments")
        st.dataframe(commits, use_container_width=True, hide_index=True)

        st.markdown("#### Update payment")
        row_opts = {f"{r['name']} — ${r['amount_due']:.0f} ({r['payment_status']})": r["id"] for _, r in commits.iterrows()}
        rsel = st.selectbox("Person", list(row_opts.keys()))
        new_paid = st.number_input("Amount paid", min_value=0.0, step=25.0)
        new_status = st.selectbox("Payment status", ["Pending", "Partial", "Paid"], key="paystat")
        if st.button("Save payment", use_container_width=True):
            conn.execute("UPDATE commitments SET amount_paid=?, payment_status=? WHERE id=?",
                         (new_paid, new_status, row_opts[rsel]))
            conn.commit()
            st.success("Saved")
            st.rerun()
    else:
        st.write("No one added to this drop yet.")
    conn.close()

# ─── MONEY ──────────────────────────────────────────────────
elif page == "Money":
    st.title("Money")

    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT cy.id, cy.name, cy.status,
               COALESCE(SUM(cm.lbs),0) as lbs,
               COALESCE(SUM(cm.amount_paid),0) as collected,
               COALESCE(SUM(cm.lbs * cy.wholesale_price),0) as cost
        FROM cycles cy
        LEFT JOIN commitments cm ON cm.cycle_id = cy.id
        GROUP BY cy.id ORDER BY cy.id DESC
    """, conn)

    if not df.empty:
        df["profit"] = df["collected"] - df["cost"]
        st.dataframe(
            df[["name", "status", "lbs", "collected", "cost", "profit"]].rename(columns={
                "name": "Drop", "status": "Status", "lbs": "lbs",
                "collected": "Collected", "cost": "Cost", "profit": "Profit"
            }),
            use_container_width=True, hide_index=True
        )
        closed = df[df["status"] == "Closed"]
        if not closed.empty:
            st.metric("Total closed profit", f"${closed['profit'].sum():,.0f}")
    else:
        st.write("No data yet.")

    st.divider()
    fund = float(get_setting("reinvestment_fund", "0"))
    st.metric("Reinvestment Fund", f"${fund:,.2f}")

    col1, col2 = st.columns(2)
    with col1:
        add = st.number_input("Add to fund", min_value=0.0, step=50.0, key="addf")
        if st.button("Add", use_container_width=True):
            set_setting("reinvestment_fund", fund + add)
            st.rerun()
    with col2:
        use = st.number_input("Use from fund", min_value=0.0, step=50.0, key="usef")
        if st.button("Use", use_container_width=True):
            if use <= fund:
                set_setting("reinvestment_fund", fund - use)
                st.rerun()
            else:
                st.error("Not enough")
    conn.close()

# ─── MESSAGES ───────────────────────────────────────────────
elif page == "Messages":
    st.title("Messages")
    templates = {
        "Outreach": "Hey [Name],\n\nI’m running a small group buy at $500/lb. Looking for consistent people. Want in on the next drop? Just reply with how many lbs.",
        "Drop Open": "Next drop is open.\n\nPrice: $500/lb\nClosing: [day/time]\nReply with name + lbs wanted.\n\nFirst come, first served.",
        "Payment": "You’re confirmed for [X] lbs.\nTotal: $[amount]\n\nSend to: [Cash App / Venmo / Zelle]\nOnce received I’ll lock your spot.",
        "Ordered": "Order placed. Confirmation received. Expected around [day]. I’ll message when it’s ready.",
        "Ready": "Product is in.\n\nPickup: [location / window]\nConfirm when you can grab it.",
        "Referral": "Know someone solid who wants in regularly? Send them my way. You’ll get credit on your next order for every new buyer."
    }
    choice = st.selectbox("Template", list(templates.keys()))
    st.text_area("Copy this", templates[choice], height=180)

# ─── SETTINGS ───────────────────────────────────────────────
elif page == "Settings":
    st.title("Settings")
    wh = st.number_input("Wholesale $/lb", value=float(get_setting("wholesale_price", DEFAULT_WHOLESALE)), step=1.0)
    se = st.number_input("Sell $/lb", value=float(get_setting("sell_price", DEFAULT_SELL)), step=1.0)
    if st.button("Save", use_container_width=True):
        set_setting("wholesale_price", wh)
        set_setting("sell_price", se)
        st.success("Saved")
        st.rerun()
    st.caption(f"Margin: ${se - wh:.0f} per lb")
