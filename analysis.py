"""
Analysis of app 174 performance for April 2024.

Order of work:
  1. Sanity checks on the raw data
  2. Two cleaned tables built in SQL: installs without duplicates, and revenue
     without duplicate event ids.
  3. One analysis table (app174_base): app 174 installs in April with each
     install's April revenue attached.
  4. Headline economics, plus breakdowns by network, country, and app version.
  5. Charts written to charts/.
  6. A printed summary

Run build_database.py first, then this.

To run on a different app or month, change the config block below. Nothing
else needs changing.
"""

import sqlite3
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path


# Config
DB_PATH = "app174.db"
APP_ID = 174
MONTH_START = "2024-04-01"
MONTH_END = "2024-04-30"
BID = 2.0             # paid to the network per install
CASHOUT_RATE = 0.10   # share of revenue paid back to users
CHART_DIR = Path("charts")

BREAKEVEN_ARPI = BID / (1 - CASHOUT_RATE)  # revenue per install where profit = 0


def q(conn, sql):
    return pd.read_sql_query(sql, conn)



# Sanity Checks
def run_sanity_checks(conn):
    print("=" * 64)
    print("SANITY CHECKS")
    print("=" * 64)

    apps = q(conn, "SELECT DISTINCT client FROM installs_raw ORDER BY client")
    print("Apps in installs file:", list(apps["client"]))

    r = q(conn, "SELECT MIN(install_event_date) a, MAX(install_event_date) b FROM installs_raw").iloc[0]
    print("Install dates:", r["a"], "to", r["b"])
    
    r = q(conn, "SELECT MIN(event_date) a, MAX(event_date) b FROM revenue_raw").iloc[0]
    print("Revenue dates:", r["a"], "to", r["b"])

    # duplicate installs
    d = q(conn, "SELECT COUNT(*) - COUNT(DISTINCT user_install_id) n FROM installs_raw").iloc[0]["n"]
    print("Duplicate install rows:", int(d))

    # duplicate revenue event ids
    d = q(conn, "SELECT COUNT(*) - COUNT(DISTINCT id) n FROM revenue_raw").iloc[0]["n"]
    print("Duplicate revenue rows (same event id):", int(d))

    # revenue with no install id, whole file and April only
    full = q(conn, """
        SELECT COUNT(*) c, ROUND(SUM(money_value_usd),2) usd
        FROM revenue_raw WHERE user_install_id IS NULL
    """).iloc[0]
    apr = q(conn, f"""
        SELECT COUNT(*) c, ROUND(SUM(money_value_usd),2) usd
        FROM revenue_raw
        WHERE user_install_id IS NULL
          AND event_date >= '{MONTH_START}' AND event_date <= '{MONTH_END}'
    """).iloc[0]
    print(f"Revenue with no install id, whole file: {int(full['c']):,} rows, ${full['usd']:,.2f}")
    print(f"Revenue with no install id, April only: {int(apr['c']):,} rows, ${apr['usd']:,.2f}")

    # revenue pointing to an install id that does not exist
    orph = q(conn, """
        SELECT COUNT(*) c, ROUND(SUM(r.money_value_usd),2) usd
        FROM revenue_raw r
        LEFT JOIN (SELECT DISTINCT user_install_id FROM installs_raw) i
               ON r.user_install_id = i.user_install_id
        WHERE r.user_install_id IS NOT NULL AND i.user_install_id IS NULL
    """).iloc[0]
    print(f"Revenue with unknown install id: {int(orph['c']):,} rows, ${orph['usd']:,.2f}")

    # negative revenue
    neg = q(conn, "SELECT COUNT(*) c, ROUND(SUM(money_value_usd),2) usd FROM revenue_raw WHERE money_value_usd < 0").iloc[0]
    print(f"Negative revenue events: {int(neg['c'])}, ${neg['usd']:,.2f}")

    # event_count = 0 but still carries money
    z = q(conn, "SELECT COUNT(*) c, ROUND(SUM(money_value_usd),2) usd FROM revenue_raw WHERE event_count = 0").iloc[0]
    print(f"Rows with event_count = 0 but nonzero money: {int(z['c'])}, ${z['usd']:,.2f}")

    # revenue timestamped before install: strict date vs same-day
    ts = q(conn, """
        SELECT
          SUM(CASE WHEN r.event_timestamp < i.install_ts THEN 1 ELSE 0 END) AS ts_before,
          SUM(CASE WHEN r.event_date < i.install_date THEN 1 ELSE 0 END) AS date_before
        FROM revenue_raw r
        JOIN (
            SELECT user_install_id,
                   MIN(install_event_date) install_date,
                   MIN(install_event_timestamp) install_ts
            FROM installs_raw GROUP BY user_install_id
        ) i ON r.user_install_id = i.user_install_id
    """).iloc[0]
    print(f"Revenue before install: {int(ts['ts_before'])} by timestamp, "
          f"{int(ts['date_before'])} by date (rest are same-day, likely timestamp precision)")
    print()



# Clean tables + Analysis Base
def build_clean_tables(conn):
    conn.executescript(f"""
        -- one row per install, keeping the copy that has a country
        DROP TABLE IF EXISTS installs_clean;
        CREATE TABLE installs_clean AS
        WITH ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY user_install_id
                       ORDER BY CASE WHEN geo_country_code IS NULL THEN 1 ELSE 0 END
                   ) AS rn
            FROM installs_raw
        )
        SELECT user_install_id, client, geo_country_code, client_version,
               network_id, install_event_date
        FROM ranked WHERE rn = 1;

        -- one row per revenue event id, keeping the copy that has an install id
        DROP TABLE IF EXISTS revenue_clean;
        CREATE TABLE revenue_clean AS
        WITH ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY id
                       ORDER BY CASE WHEN user_install_id IS NULL THEN 1 ELSE 0 END
                   ) AS rn
            FROM revenue_raw
        )
        SELECT id, user_install_id, money_value_usd, event_count, event_date
        FROM ranked WHERE rn = 1;

        -- app 174 installs in the month, with each install's month revenue
        DROP TABLE IF EXISTS app174_base;
        CREATE TABLE app174_base AS
        WITH app_installs AS (
            SELECT user_install_id, geo_country_code, client_version,
                   network_id, install_event_date
            FROM installs_clean
            WHERE client = {APP_ID}
              AND install_event_date >= '{MONTH_START}'
              AND install_event_date <= '{MONTH_END}'
        ),
        month_revenue AS (
            SELECT user_install_id, SUM(money_value_usd) AS revenue
            FROM revenue_clean
            WHERE user_install_id IS NOT NULL
              AND event_date >= '{MONTH_START}'
              AND event_date <= '{MONTH_END}'
            GROUP BY user_install_id
        )
        SELECT a.user_install_id, a.geo_country_code, a.client_version,
               a.network_id, a.install_event_date,
               COALESCE(m.revenue, 0) AS revenue
        FROM app_installs a
        LEFT JOIN month_revenue m ON a.user_install_id = m.user_install_id;
    """)
    conn.commit()
    n = q(conn, "SELECT COUNT(*) n FROM app174_base").iloc[0]["n"]
    print(f"Clean base built: {int(n):,} app-{APP_ID} installs in window\n")



# Metrics
def headline(conn):
    b = q(conn, """
        SELECT COUNT(*) installs, SUM(revenue) gross_revenue,
               SUM(CASE WHEN revenue > 0 THEN 1 ELSE 0 END) paying_users
        FROM app174_base
    """).iloc[0]
    installs = int(b["installs"])
    gross = float(b["gross_revenue"])
    payers = int(b["paying_users"])
    acq = installs * BID
    cashout = gross * CASHOUT_RATE
    net = gross - cashout - acq
    return {
        "installs": installs, "gross_revenue": gross, "acq_cost": acq,
        "cashout": cashout, "net_profit": net,
        "gross_roas": gross / acq,
        "net_roas": (gross - cashout) / acq,
        "roi": net / acq,
        "arpi": gross / installs,
        "paying_users": payers, "conversion": payers / installs,
        "arppu": gross / payers,
    }


def by_dimension(conn, dim):
    return q(conn, f"""
        SELECT {dim} AS segment,
               COUNT(*) AS installs,
               ROUND(SUM(revenue), 2) AS gross_revenue,
               ROUND(SUM(revenue) * 1.0 / COUNT(*), 4) AS arpi,
               ROUND(SUM(CASE WHEN revenue > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS pay_rate,
               ROUND(SUM(revenue) * (1 - {CASHOUT_RATE}) - COUNT(*) * {BID}, 2) AS net_profit,
               CASE WHEN SUM(revenue) * 1.0 / COUNT(*) >= {BREAKEVEN_ARPI}
                    THEN 'profitable' ELSE 'loss' END AS status
        FROM app174_base
        GROUP BY {dim}
        ORDER BY net_profit DESC
    """)

# It means total April revenue generated by installs acquired on that day. 
# It does not mean revenue events that occurred on that day because the revenue column is at install grain:
# revenue: One row per user_install_id, with that install’s total April revenue attached.
def daily(conn):
    return q(conn, f"""
        SELECT install_event_date AS day,
               COUNT(*) AS installs,
               ROUND(SUM(revenue) * (1 - {CASHOUT_RATE}) - COUNT(*) * {BID}, 2) AS net_profit
        FROM app174_base
        GROUP BY install_event_date
        ORDER BY install_event_date
    """)



# Charts
GREEN, RED, BLUE = "#2f6b4d", "#9b2c2c", "#1e3a5f"


def setup_style():
    plt.rcParams.update({
        "figure.dpi": 110, "savefig.bbox": "tight",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.25, "font.size": 11,
    })


def bar_profit(df, label_col, title, fname, min_installs=0):
    d = df[df["installs"] >= min_installs].sort_values("net_profit")
    colors = [GREEN if v > 0 else RED for v in d["net_profit"]]
    fig, ax = plt.subplots(figsize=(8, max(3.5, 0.4 * len(d) + 1.5)))
    ax.barh(d[label_col].astype(str), d["net_profit"], color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Net profit (USD)")
    ax.set_ylabel(label_col.replace("_", " "))
    ax.set_title(title)
    fig.savefig(CHART_DIR / fname)
    plt.close(fig)


def chart_arpi_network(net_df):
    d = net_df.sort_values("arpi", ascending=False)
    colors = [GREEN if v >= BREAKEVEN_ARPI else RED for v in d["arpi"]]
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.bar(d["segment"].astype(str), d["arpi"], color=colors)
    ax.axhline(BREAKEVEN_ARPI, color="black", linestyle="--", linewidth=1,
               label=f"Break-even ${BREAKEVEN_ARPI:.2f}")
    ax.set_xlabel("Network id")
    ax.set_ylabel("Revenue per install (USD)")
    ax.set_title("Revenue per install by network vs break-even, app 174, April 2024")
    ax.legend()
    plt.xticks(rotation=90)
    fig.savefig(CHART_DIR / "arpi_by_network.png")
    plt.close(fig)


def chart_country(country_df):
    d = country_df.sort_values("net_profit", ascending=False)
    colors = [GREEN if v > 0 else RED for v in d["net_profit"]]
    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.bar(d["segment"].astype(str), d["net_profit"], color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Country")
    ax.set_ylabel("Net profit (USD)")
    ax.set_title("Net profit by country, app 174, April 2024")
    fig.savefig(CHART_DIR / "profit_by_country.png")
    plt.close(fig)


def chart_daily(daily_df):
    d = daily_df.copy()
    d["day"] = pd.to_datetime(d["day"])
    fig, ax1 = plt.subplots(figsize=(9, 4.5))
    ax1.bar(d["day"], d["installs"], color="#cdd6e0", width=0.8)
    ax1.set_ylabel("Installs", color=BLUE)
    ax1.set_xlabel("Install day")
    ax2 = ax1.twinx()
    ax2.plot(d["day"], d["net_profit"], color=BLUE, marker="o", markersize=3, linewidth=1.5)
    ax2.axhline(0, color=RED, linewidth=0.8, linestyle="--")
    ax2.set_ylabel("Net profit (USD)", color=BLUE)
    ax2.grid(False)
    ax1.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax1.set_title("Daily installs and net profit by install day, app 174, April 2024")
    fig.savefig(CHART_DIR / "daily_trend.png")
    plt.close(fig)


def chart_opportunity(net_df, current_net):
    keep = net_df[net_df["net_profit"] > 0]["net_profit"].sum()
    fig, ax = plt.subplots(figsize=(6, 4.5))
    bars = ax.bar(["All networks\n(today)", "Profitable\nnetworks only"],
                  [current_net, keep], color=[BLUE, GREEN])
    ax.set_ylabel("Net profit (USD)")
    ax.set_title("Profit today vs profit if loss-making networks are cut")
    for b, v in zip(bars, [current_net, keep]):
        ax.text(b.get_x() + b.get_width() / 2, v, f"${v:,.0f}", ha="center", va="bottom")
    fig.savefig(CHART_DIR / "profit_opportunity.png")
    plt.close(fig)


# Main
def main():
    CHART_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    run_sanity_checks(conn)
    build_clean_tables(conn)

    h = headline(conn)
    net_df = by_dimension(conn, "network_id")
    country_df = by_dimension(conn, "geo_country_code")
    version_df = by_dimension(conn, "client_version")
    daily_df = daily(conn)

    setup_style()
    bar_profit(net_df, "segment", "Net profit by network, app 174, April 2024",
               "net_profit_by_network.png")
    chart_arpi_network(net_df)
    chart_country(country_df)
    bar_profit(version_df, "segment", "Net profit by app version (100+ installs), app 174, April 2024",
               "net_profit_by_version.png", min_installs=100)
    chart_daily(daily_df)
    chart_opportunity(net_df, h["net_profit"])

    print("=" * 64)
    print(f"SUMMARY: app {APP_ID}, {MONTH_START} to {MONTH_END}")
    print("=" * 64)
    print(f"Installs:              {h['installs']:,}")
    print(f"Acquisition cost:      ${h['acq_cost']:,.2f}")
    print(f"Gross revenue:         ${h['gross_revenue']:,.2f}")
    print(f"Cashout to users:      ${h['cashout']:,.2f}")
    print(f"Net profit:            ${h['net_profit']:,.2f}")
    print(f"Gross ROAS:            {h['gross_roas']:.4f}x   (revenue / ad spend)")
    print(f"Net ROAS:              {h['net_roas']:.4f}x   (revenue after cashout / ad spend)")
    print(f"ROI on ad spend:       {h['roi']*100:.2f}%")
    print(f"Revenue per install:   ${h['arpi']:.4f}   (break-even ${BREAKEVEN_ARPI:.2f})")
    print(f"Paying-user rate:      {h['conversion']*100:.1f}%")
    print(f"Revenue per payer:     ${h['arppu']:.2f}")

    print("\nBy country:")
    print(country_df.to_string(index=False))
    print("\nBy network:")
    print(net_df.to_string(index=False))
    print("\nBy app version:")
    print(version_df.to_string(index=False))

    w = net_df[net_df["net_profit"] > 0]
    l = net_df[net_df["net_profit"] <= 0]
    print(f"\nProfitable networks: {len(w)} (net +${w['net_profit'].sum():,.0f}, {int(w['installs'].sum()):,} installs)")
    print(f"Loss-making networks: {len(l)} (net ${l['net_profit'].sum():,.0f}, {int(l['installs'].sum()):,} installs)")
    print("\nCharts in:", CHART_DIR.resolve())
    conn.close()


if __name__ == "__main__":
    main()
