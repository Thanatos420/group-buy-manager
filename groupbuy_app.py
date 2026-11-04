#!/usr/bin/env python3
"""
Group Buy Manager — Streamlit App
Bulk Purchase & Reinvestment System
"""

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
from pathlib import Path
import json

# CONFIG & DATABASE
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
    c.execute("""CREATE TABLE IF NOT EXISTS buyers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, contact TEXT, status TEXT DEFAULT 'Prospect', typical_lbs REAL DEFAULT 1.0, last_cycle_date TEXT, total_cycles INTEGER DEFAULT 0, referred_by TEXT, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS cycles (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, status TEXT DEFAULT 'Open', opened_date TEXT, closed_date TEXT, wholesale_price REAL, sell_price REAL, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS commitments (id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id INTEGER, buyer_id INTEGER, lbs REAL, amount_due REAL, amount_paid REAL DEFAULT 0, payment_status TEXT DEFAULT 'Pending', notes TEXT, FOREIGN KEY (cycle_id) REFERENCES cycles(id), FOREIGN KEY (buyer_id) REFERENCES buyers(id))""")
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

st.set_page_config(page_title="Group Buy Manager", page_icon="📦", layout="wide", initial_sidebar_state="expanded")
init_db()

st.sidebar.title("📦 Group Buy Manager")
st.sidebar.caption("Bulk Purchase • Reinvestment • Low Overhead")
page = st.sidebar.radio("Navigate", ["Dashboard", "Buyers", "Cycles", "Current Cycle Detail", "Finances", "Templates", "Settings"], label_visibility="collapsed")
st.sidebar.markdown("---")
wholesale = float(get_setting("wholesale_price", DEFAULT_WHOLESALE))
sell = float(get_setting("sell_price", DEFAULT_SELL))
margin = sell - wholesale
st.sidebar.metric("Wholesale", f"${wholesale:.0f}/lb")
st.sidebar.metric("Sell Price", f"${sell:.0f}/lb")
st.sidebar.metric("Margin", f"${margin:.0f}/lb")

if page == "Dashboard":
    st.title("Dashboard")
    st.caption("Quick overview of your group-buy operation")
    conn = get_conn()
    active_count = conn.execute("SELECT COUNT(*) FROM buyers WHERE status = 'Active'").fetchone()[0]
    total_buyers = conn.execute("SELECT COUNT(*) FROM buyers").fetchone()[0]
    open_cycle = conn.execute("SELECT * FROM cycles WHERE status IN ('Open', 'Collecting', 'Ordered', 'Received') ORDER BY id DESC LIMIT 1").fetchone()
    total_profit = conn.execute("SELECT COALESCE(SUM(c.amount_paid - (c.lbs * cy.wholesale_price)), 0) FROM commitments c JOIN cycles cy ON c.cycle_id = cy.id WHERE c.payment_status = 'Paid' AND cy.status = 'Closed'").fetchone()[0]
    reinvestment = float(get_setting("reinvestment_fund", "0"))
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Active Buyers", active_count)
    col2.metric("Total Buyers", total_buyers)
    col3.metric("Lifetime Profit (Closed)", f"${total_profit:,.0f}")
    col4.metric("Reinvestment Fund", f"${reinvestment:,.0f}")
    st.markdown("---")
    if open_cycle:
        cycle_label = open_cycle["name"] if open_cycle["name"] else f"Cycle #{open_cycle['id']}"
        st.subheader(f"Current Cycle: {cycle_label}")
        st.write(f"**Status:** {open_cycle['status']}  |  **Opened:** {open_cycle['opened_date'] or '—'}")
        commits = conn.execute("SELECT COALESCE(SUM(lbs), 0) as total_lbs, COALESCE(SUM(amount_due), 0) as total_due, COALESCE(SUM(amount_paid), 0) as total_paid, COUNT(*) as num_people FROM commitments WHERE cycle_id = ?", (open_cycle["id"],)).fetchone()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("People In", commits["num_people"])
        c2.metric("Total lbs", f"{commits['total_lbs']:.2f}")
        c3.metric("Collected", f"${commits['total_paid']:,.0f}")
        c4.metric("Still Due", f"${commits['total_due'] - commits['total_paid']:,.0f}")
    else:
        st.info("No open cycle right now. Go to **Cycles** to start one.")
    conn.close()

elif page == "Buyers":
    st.title("Buyers")
    st.caption("Manage your people")
    tab1, tab2 = st.tabs(["Buyer List", "Add / Edit Buyer"])
    with tab1:
        conn = get_conn()
        df = pd.read_sql_query("SELECT id, name, contact, status, typical_lbs, total_cycles, last_cycle_date, referred_by, notes FROM buyers ORDER BY status, name", conn)
        st.dataframe(df, use_container_width=True, hide_index=True)
        conn.close()
    with tab2:
        conn = get_conn()
        with st.form("add_buyer"):
            name = st.text_input("Name *")
            contact = st.text_input("Contact")
            status = st.selectbox("Status", ["Prospect", "New", "Active", "Occasional", "Inactive"])
            typical = st.number_input("Typical lbs", min_value=0.25, value=1.0, step=0.25)
            referred = st.text_input("Referred by")
            notes = st.text_area("Notes")
            if st.form_submit_button("Add Buyer"):
                if name.strip():
                    conn.execute("INSERT INTO buyers (name, contact, status, typical_lbs, referred_by, notes) VALUES (?, ?, ?, ?, ?, ?)", (name.strip(), contact, status, typical, referred, notes))
                    conn.commit()
                    st.success(f"Added {name}")
                    st.rerun()
        conn.close()

elif page == "Cycles":
    st.title("Cycles")
    conn = get_conn()
    with st.expander("Start New Cycle", expanded=False):
        with st.form("new_cycle"):
            cname = st.text_input("Cycle name (optional)")
            opened = st.date_input("Opened date", value=date.today())
            wh = st.number_input("Wholesale $/lb", value=wholesale, step=1.0)
            se = st.number_input("Sell $/lb", value=sell, step=1.0)
            notes = st.text_area("Notes")
            if st.form_submit_button("Create Cycle"):
                conn.execute("INSERT INTO cycles (name, status, opened_date, wholesale_price, sell_price, notes) VALUES (?, 'Open', ?, ?, ?, ?)", (cname or None, opened.isoformat(), wh, se, notes))
                conn.commit()
                st.success("Cycle created.")
                st.rerun()
    cycles_df = pd.read_sql_query("SELECT id, name, status, opened_date, closed_date, wholesale_price, sell_price FROM cycles ORDER BY id DESC", conn)
    st.dataframe(cycles_df, use_container_width=True, hide_index=True)
    conn.close()

elif page == "Current Cycle Detail":
    st.title("Current Cycle Detail")
    conn = get_conn()
    cycles = conn.execute("SELECT id, name, status, wholesale_price, sell_price FROM cycles ORDER BY id DESC").fetchall()
    if not cycles:
        st.warning("No cycles exist. Create one first.")
        st.stop()
    opts = {f"#{c['id']} — {c['name'] or 'Unnamed'} ({c['status']})": c for c in cycles}
    selected_label = st.selectbox("Select cycle", list(opts.keys()))
    cycle = opts[selected_label]
    cid = cycle["id"]
    st.write(f"**Wholesale:** ${cycle['wholesale_price']:.0f}/lb  •  **Sell:** ${cycle['sell_price']:.0f}/lb")
    with st.expander("Add Commitment", expanded=True):
        buyers = conn.execute("SELECT id, name, typical_lbs FROM buyers ORDER BY name").fetchall()
        if buyers:
            bopts = {f"{b['name']} (typical {b['typical_lbs']} lb)": b for b in buyers}
            with st.form("add_commit"):
                bsel = st.selectbox("Buyer", list(bopts.keys()))
                lbs = st.number_input("lbs", min_value=0.25, value=float(bopts[bsel]["typical_lbs"] or 1.0), step=0.25)
                amount = lbs * cycle["sell_price"]
                st.write(f"Amount due: **${amount:.2f}**")
                paid = st.number_input("Amount already paid", min_value=0.0, value=0.0, step=25.0)
                pstatus = st.selectbox("Payment status", ["Pending", "Partial", "Paid"])
                if st.form_submit_button("Add to Cycle"):
                    buyer = bopts[bsel]
                    conn.execute("INSERT INTO commitments (cycle_id, buyer_id, lbs, amount_due, amount_paid, payment_status) VALUES (?, ?, ?, ?, ?, ?)", (cid, buyer["id"], lbs, amount, paid, pstatus))
                    conn.commit()
                    st.success("Added.")
                    st.rerun()
    commits = pd.read_sql_query("SELECT cm.id, b.name, cm.lbs, cm.amount_due, cm.amount_paid, cm.payment_status FROM commitments cm JOIN buyers b ON cm.buyer_id = b.id WHERE cm.cycle_id = ? ORDER BY b.name", conn, params=(cid,))
    st.dataframe(commits, use_container_width=True, hide_index=True)
    conn.close()

elif page == "Finances":
    st.title("Finances")
    conn = get_conn()
    df = pd.read_sql_query("SELECT cy.id, cy.name, cy.status, COALESCE(SUM(cm.lbs), 0) as total_lbs, COALESCE(SUM(cm.amount_paid), 0) as collected, COALESCE(SUM(cm.lbs * cy.wholesale_price), 0) as cost FROM cycles cy LEFT JOIN commitments cm ON cm.cycle_id = cy.id GROUP BY cy.id ORDER BY cy.id DESC", conn)
    if not df.empty:
        df["profit"] = df["collected"] - df["cost"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    current_fund = float(get_setting("reinvestment_fund", "0"))
    st.metric("Current Fund Balance", f"${current_fund:,.2f}")
    conn.close()

elif page == "Templates":
    st.title("Message Templates")
    templates = {
        "Initial Outreach": "Hey [Name],\n\nI’m putting together a small group buy...",
        "Drop Open": "Next drop is open.\n\nPrice: $500 / lb\nClosing: [Day/Date + time]\nReply with your name + how many lbs you want.",
        "Payment Request": "You’re confirmed for [X] lbs.\n\nTotal: $[X × 500]\nPlease send to: [Cash App / Venmo / Zelle]",
        "Order Placed": "Order has been placed.\nConfirmation received.\nExpected arrival around [day].",
        "Ready for Pickup": "Product is in.\n\nPickup details: [location / time window]",
        "Referral Offer": "If you know someone solid who would want in regularly, send them my way."
    }
    choice = st.selectbox("Choose template", list(templates.keys()))
    st.text_area("Template", templates[choice], height=220)

elif page == "Settings":
    st.title("Settings")
    wh = st.number_input("Default Wholesale $/lb", value=float(get_setting("wholesale_price", DEFAULT_WHOLESALE)), step=1.0)
    se = st.number_input("Default Sell $/lb", value=float(get_setting("sell_price", DEFAULT_SELL)), step=1.0)
    if st.button("Save Prices"):
        set_setting("wholesale_price", wh)
        set_setting("sell_price", se)
        st.success("Saved.")
        st.rerun()
    st.write(f"Current margin: **${se - wh:.0f} per lb**")
