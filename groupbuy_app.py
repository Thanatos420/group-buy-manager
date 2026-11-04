#!/usr/bin/env python3
"""
Group Buy Manager - Simple version
Easy daily use
"""

import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
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
        status TEXT DEFAULT 'Active',
        typical_lbs REAL DEFAULT 1.0,
        notes TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        status TEXT DEFAULT 'Open',
        opened_date TEXT,
        wholesale_price REAL,
        sell_price REAL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS commitments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cycle_id INTEGER,
        buyer_id INTEGER,
        lbs REAL,
        amount_due REAL,
        amount_paid REAL DEFAULT 0,
        paid INTEGER DEFAULT 0
    )""")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wholesale_price', ?)", (str(DEFAULT_WHOLESALE),))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sell_price', ?)", (str(DEFAULT_SELL),))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('reinvestment_fund', '0')")
    conn.commit()
    conn.close()

def get_setting(key, default=""):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, str(value)))
    conn.commit()
    conn.close()

def month_name(d=None):
    d = d or date.today()
    return d.strftime("%b Drop")

st.set_page_config(page_title="Group Buy", page_icon="📦", layout="centered", initial_sidebar_state="collapsed")
init_db()

st.markdown("""
<style>
    .stApp { max-width: 520px; margin: auto; }
    .block-container { padding-top: 1rem; padding-bottom: 3rem; }
    h1 { font-size: 1.5rem !important; margin-bottom: 0.2rem !important; }
    div[data-testid="stMetric"] {
        background: #f2f2f7;
        border-radius: 12px;
        padding: 10px 14px;
    }
    .stButton > button {
        border-radius: 12px;
        height: 2.6rem;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# Simple top nav
page = st.radio("", ["Drop", "People", "History", "Settings"], horizontal=True, label_visibility="collapsed")

wholesale = float(get_setting("wholesale_price", DEFAULT_WHOLESALE))
sell = float(get_setting("sell_price", DEFAULT_SELL))

# ══════════════════════════════════════════════
# DROP (main daily screen)
# ══════════════════════════════════════════════
if page == "Drop":
    st.title("Current Drop")

    conn = get_conn()
    cycle = conn.execute(
        "SELECT * FROM cycles WHERE status != 'Closed' ORDER BY id DESC LIMIT 1"
    ).fetchone()

    # No open drop → create one fast
    if not cycle:
        st.info("No open drop yet")
        if st.button(f"Start {month_name()}", use_container_width=True, type="primary"):
            conn.execute(
                "INSERT INTO cycles (name, status, opened_date, wholesale_price, sell_price) VALUES (?,?,?,?,?)",
                (month_name(), "Open", date.today().isoformat(), wholesale, sell)
            )
            conn.commit()
            st.rerun()
        conn.close()
        st.stop()

    # Show current drop
    st.subheader(cycle["name"])
    st.caption(f"Status: {cycle['status']}  ·  ${cycle['sell_price']:.0f}/lb")

    stats = conn.execute("""
        SELECT COUNT(*) as people,
               COALESCE(SUM(lbs),0) as lbs,
               COALESCE(SUM(amount_due),0) as due,
               COALESCE(SUM(amount_paid),0) as paid
        FROM commitments WHERE cycle_id = ?
    """, (cycle["id"],)).fetchone()

    c1, c2, c3 = st.columns(3)
    c1.metric("People", stats["people"])
    c2.metric("lbs", f"{stats['lbs']:.2f}")
    c3.metric("Collected", f"${stats['paid']:,.0f}")

    still_due = stats["due"] - stats["paid"]
    if still_due > 0:
        st.caption(f"${still_due:,.0f} still outstanding")

    st.divider()

    # Quick add person
    st.markdown("**Add someone**")
    buyers = conn.execute("SELECT id, name, typical_lbs FROM buyers ORDER BY name").fetchall()

    if not buyers:
        st.warning("Add people first in the People tab")
    else:
        with st.form("quick_add", clear_on_submit=True):
            bmap = {b["name"]: b for b in buyers}
            name = st.selectbox("Person", list(bmap.keys()))
            lbs = st.number_input("lbs", min_value=0.25, value=float(bmap[name]["typical_lbs"] or 1.0), step=0.25)
            amount = round(lbs * cycle["sell_price"], 2)
            st.write(f"Due: **${amount:.2f}**")
            already_paid = st.checkbox("Already paid")
            if st.form_submit_button("Add to drop", use_container_width=True, type="primary"):
                b = bmap[name]
                paid_amt = amount if already_paid else 0.0
                conn.execute(
                    "INSERT INTO commitments (cycle_id, buyer_id, lbs, amount_due, amount_paid, paid) VALUES (?,?,?,?,?,?)",
                    (cycle["id"], b["id"], lbs, amount, paid_amt, 1 if already_paid else 0)
                )
                conn.commit()
                st.success("Added")
                st.rerun()

    # Who is in this drop
    commits = pd.read_sql_query("""
        SELECT cm.id, b.name, cm.lbs, cm.amount_due, cm.amount_paid, cm.paid
        FROM commitments cm
        JOIN buyers b ON b.id = cm.buyer_id
        WHERE cm.cycle_id = ?
        ORDER BY cm.paid ASC, b.name
    """, conn, params=(cycle["id"],))

    if not commits.empty:
        st.markdown("**In this drop**")
        for _, row in commits.iterrows():
            status = "✅" if row["paid"] else "⏳"
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"{status} **{row['name']}** — {row['lbs']} lb — ${row['amount_due']:.0f}")
            with col2:
                if not row["paid"]:
                    if st.button("Mark paid", key=f"pay_{row['id']}", use_container_width=True):
                        conn.execute(
                            "UPDATE commitments SET amount_paid=?, paid=1 WHERE id=?",
                            (row["amount_due"], row["id"])
                        )
                        conn.commit()
                        st.rerun()

    st.divider()

    # Status controls
    st.markdown("**Drop controls**")
    sc1, sc2 = st.columns(2)
    with sc1:
        if cycle["status"] != "Closed":
            if st.button("Mark Ordered", use_container_width=True):
                conn.execute("UPDATE cycles SET status='Ordered' WHERE id=?", (cycle["id"],))
                conn.commit()
                st.rerun()
    with sc2:
        if st.button("Close Drop", use_container_width=True):
            conn.execute("UPDATE cycles SET status='Closed' WHERE id=?", (cycle["id"],))
            conn.commit()
            st.rerun()

    conn.close()

# ══════════════════════════════════════════════
# PEOPLE
# ══════════════════════════════════════════════
elif page == "People":
    st.title("People")

    tab_add, tab_list, tab_remove = st.tabs(["Add", "List", "Remove"])

    with tab_add:
        with st.form("add_person", clear_on_submit=True):
            name = st.text_input("Name")
            contact = st.text_input("Contact (optional)")
            typical = st.number_input("Usual lbs", min_value=0.25, value=1.0, step=0.25)
            if st.form_submit_button("Add Person", use_container_width=True, type="primary"):
                if name.strip():
                    conn = get_conn()
                    conn.execute(
                        "INSERT INTO buyers (name, contact, typical_lbs, status) VALUES (?,?,?,'Active')",
                        (name.strip(), contact, typical)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"Added {name}")
                    st.rerun()
                else:
                    st.error("Name needed")

    with tab_list:
        conn = get_conn()
        people = pd.read_sql_query(
            "SELECT name, typical_lbs, contact, status FROM buyers ORDER BY name", conn
        )
        if people.empty:
            st.write("No one added yet")
        else:
            st.dataframe(people, use_container_width=True, hide_index=True)
        conn.close()

    with tab_remove:
        conn = get_conn()
        rows = conn.execute("SELECT id, name FROM buyers ORDER BY name").fetchall()
        if not rows:
            st.write("Nothing to remove")
        else:
            options = {r["name"]: r["id"] for r in rows}
            pick = st.selectbox("Who to remove", list(options.keys()))
            if st.button("Remove", type="primary", use_container_width=True):
                bid = options[pick]
                conn.execute("DELETE FROM commitments WHERE buyer_id=?", (bid,))
                conn.execute("DELETE FROM buyers WHERE id=?", (bid,))
                conn.commit()
                st.success("Removed")
                st.rerun()
        conn.close()

# ══════════════════════════════════════════════
# HISTORY
# ══════════════════════════════════════════════
elif page == "History":
    st.title("History")

    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT cy.name, cy.status,
               COALESCE(SUM(cm.lbs),0) as lbs,
               COALESCE(SUM(cm.amount_paid),0) as collected,
               COALESCE(SUM(cm.lbs * cy.wholesale_price),0) as cost
        FROM cycles cy
        LEFT JOIN commitments cm ON cm.cycle_id = cy.id
        GROUP BY cy.id
        ORDER BY cy.id DESC
    """, conn)

    if df.empty:
        st.write("No drops yet")
    else:
        df["profit"] = df["collected"] - df["cost"]
        st.dataframe(
            df.rename(columns={
                "name": "Drop", "status": "Status", "lbs": "lbs",
                "collected": "In", "cost": "Cost", "profit": "Profit"
            }),
            use_container_width=True, hide_index=True
        )

    fund = float(get_setting("reinvestment_fund", "0"))
    st.metric("Reinvestment Fund", f"${fund:,.0f}")

    a, b = st.columns(2)
    with a:
        add = st.number_input("Add to fund", min_value=0.0, step=50.0, key="af")
        if st.button("Add", use_container_width=True):
            set_setting("reinvestment_fund", fund + add)
            st.rerun()
    with b:
        use = st.number_input("Take from fund", min_value=0.0, step=50.0, key="uf")
        if st.button("Take", use_container_width=True):
            if use <= fund:
                set_setting("reinvestment_fund", fund - use)
                st.rerun()
    conn.close()

# ══════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════
elif page == "Settings":
    st.title("Settings")

    wh = st.number_input("Wholesale price", value=wholesale, step=1.0)
    se = st.number_input("Sell price", value=sell, step=1.0)

    if st.button("Save prices", use_container_width=True, type="primary"):
        set_setting("wholesale_price", wh)
        set_setting("sell_price", se)
        st.success("Saved")
        st.rerun()

    st.caption(f"Current margin: ${se - wh:.0f} per lb")

    st.divider()
    st.caption("To use as an app on iPhone: open this page in Safari → Share → Add to Home Screen")
