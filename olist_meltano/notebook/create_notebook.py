#!/usr/bin/env python3
"""Run once to generate olist_analysis.ipynb in the same directory."""
import json, pathlib

OUT = pathlib.Path(__file__).parent / 'olist_analysis.ipynb'

def md(src):
    return {"cell_type": "markdown", "metadata": {}, "source": src}

def code(src):
    return {"cell_type": "code", "execution_count": None,
            "metadata": {}, "outputs": [], "source": src}

# ── Cells ─────────────────────────────────────────────────────────────────────

TITLE = md(
    '# Olist E-Commerce Analysis\n'
    '**Customer Loyalty · Revenue Opportunity · Geographic Coverage · Seller Health**\n\n'
    'All queries run against dbt-built mart tables in BigQuery.  \n'
    'All queries run against `olist_transformed_marts` in BigQuery.'
)

SETUP = code(
    'from google.cloud import bigquery\n'
    'import pandas as pd\n'
    'import matplotlib.pyplot as plt\n'
    'import matplotlib.ticker as mticker\n'
    'import seaborn as sns\n'
    '\n'
    '# ── Configuration ────────────────────────────────────────────────────────\n'
    "KEY_FILE = '/Users/tess/NTU/M2/Project/olist-498903-e7f8763e517a.json'\n"
    "PROJECT  = 'olist-498903'\n"
    "DATASET  = 'olist_transformed'\n"
    '\n'
    "MARTS     = f'{PROJECT}.{DATASET}_marts'\n"
    "STAGING   = f'{PROJECT}.{DATASET}_staging'\n"
    "SNAPSHOTS = f'{PROJECT}.{DATASET}_snapshots'\n"
    '\n'
    'client = bigquery.Client.from_service_account_json(KEY_FILE)\n'
    '\n'
    'def q(sql: str) -> pd.DataFrame:\n'
    '    return client.query(sql).to_dataframe()\n'
    '\n'
    "sns.set_theme(style='whitegrid', palette='muted')\n"
    "plt.rcParams['figure.dpi']       = 120\n"
    "plt.rcParams['font.size']        = 16\n"
    "plt.rcParams['axes.titlesize']   = 24\n"
    "plt.rcParams['figure.titlesize'] = 28\n"
    "plt.rcParams['axes.labelsize']   = 18\n"
    "plt.rcParams['xtick.labelsize']  = 15\n"
    "plt.rcParams['ytick.labelsize']  = 15\n"
    "plt.rcParams['legend.fontsize']  = 16\n"
    "plt.rcParams['axes.titlepad']    = 20"
)

DQ_HEADER = md(
    '## 0. Known Data Quality Issues\n\n'
    'Sourced from Great Expectations raw-layer validation (run 2026-06-13). '
    'Issues are handled either via explicit exclusion in queries below, '
    'inline query filters, or documented as context.\n\n'
    '### Excluded from queries (`EXCL_SQL`)\n'
    '| order_id | Issue |\n'
    '|---|---|\n'
    '| `bfbd0f9bdef84302105ad712db648a6c` | Delivered order with no payment record — '
    '`total_payment_value` NULL. Marts COALESCE to 0; excluded from raw queries. |\n\n'
    '### Handled via inline query filters\n'
    '| Issue | Count | Filter applied |\n'
    '|---|---|---|\n'
    '| Delivered orders missing delivery timestamp | 8 | `delivery_days IS NOT NULL` (Point 3) |\n'
    '| Review creation date before order purchase date | 74 | '
    '`DATE(fr.review_creation_date) >= DATE(fo.order_purchase_timestamp)` (Point 4) |\n'
    '| Products with NULL category name | 610 (~1.9%) | '
    '`dp.product_category_name_english IS NOT NULL` (Points 1 & 2) |\n\n'
    '### Documented — retained in data\n'
    '| Issue | Count | Severity | Notes |\n'
    '|---|---|---|---|\n'
    '| Zero or negative `payment_value` rows | 9 | Low | '
    'Revenue queries use `fo.price`, not `payment_value` — no direct impact |\n'
    '| Payment > R$5,000 (potential fraud) | 6 | Low | Retained; flagged for fraud review |\n'
    '| Installments > 12 | 185 | Medium | Outside Brazil norm; retained for analysis |\n'
    '| Orders with > 5 payment methods | 118 | Medium | Unusual but valid |\n'
    '| Payment vs item price mismatch > R$1 | 249 | Medium | '
    'Expected — installment interest and vouchers cause legitimate differences |\n'
    '| Orders with multiple distinct reviews | 547 | Medium | '
    'Handled by composite key `(review_id, order_id)` in `fact_reviews` |\n'
    '| Sellers with only 1 delivered order | 571 | Medium | '
    'Health score unreliable; shown in Point 4 distribution chart |\n'
    '| Customer zip codes missing from geolocation | 7,824 | High | '
    'NULL lat/lng — does not affect state-level analysis in Point 3 |\n'
    '| Seller zip codes missing from geolocation | 733 | Medium | '
    'NULL lat/lng for those sellers in `dim_sellers` |\n'
    '| `customer_unique_id` with multiple `customer_id`s | 3,345 | High | '
    'Expected Olist design — all analysis uses `customer_unique_id` |'
)

DQ_CODE = code(
    "EXCLUDED_ORDERS = ['bfbd0f9bdef84302105ad712db648a6c']\n"
    'EXCL_SQL = "\'" + "\', \'".join(EXCLUDED_ORDERS) + "\'"\n'
    'print(f"Excluding {len(EXCLUDED_ORDERS)} order(s): {EXCLUDED_ORDERS}")'
)

P1_HEADER = md(
    '---\n'
    '## 1. Customer Loyalty & Churn: The Category Effect\n\n'
    '**Hypothesis tested:** Why do ~97% of customers never return?  \n'
    'We tested 7 factors — geography, seller quality, product category, first-order spend, '
    'review score, payment method, and seasonality.\n\n'
    '**Finding:** None of the "bad experience" factors predict churn. '
    'The real driver is **product category**.  \n'
    'Durable goods (electronics, appliances) are naturally one-time purchases. '
    'Consumables and fashion have genuine repeat potential.\n\n'
    '**Method:** For each customer, identify their first-order category, '
    'then check whether they placed a second order on the platform.'
)

P1_QUERY = code(
    'df_churn = q(f"""\n'
    'WITH first_category AS (\n'
    '    SELECT\n'
    '        dc.customer_unique_id,\n'
    '        dp.product_category_name_english AS first_category\n'
    '    FROM `{MARTS}.fact_orders` fo\n'
    '    JOIN `{MARTS}.dim_customers` dc ON fo.customer_id  = dc.customer_id\n'
    '    JOIN `{MARTS}.dim_products`  dp ON fo.product_id   = dp.product_id\n'
    "    WHERE fo.order_status = 'delivered'\n"
    '      AND fo.order_id NOT IN ({EXCL_SQL})\n'
    '      AND dp.product_category_name_english IS NOT NULL\n'
    '    QUALIFY ROW_NUMBER() OVER (\n'
    '        PARTITION BY dc.customer_unique_id\n'
    '        ORDER BY fo.order_purchase_timestamp\n'
    '    ) = 1\n'
    ')\n'
    'SELECT\n'
    '    fc.first_category                              AS category,\n'
    '    COUNT(*)                                       AS cohort_size,\n'
    '    COUNTIF(mcs.total_orders > 1)                 AS returned,\n'
    '    ROUND(COUNTIF(mcs.total_orders > 1)\n'
    '          / COUNT(*) * 100, 1)                    AS return_rate_pct\n'
    'FROM first_category fc\n'
    'JOIN `{MARTS}.mart_customer_summary` mcs\n'
    '    ON fc.customer_unique_id = mcs.customer_unique_id\n'
    'GROUP BY category\n'
    'HAVING cohort_size >= 50\n'
    'ORDER BY return_rate_pct DESC\n'
    '""")\n'
    'df_churn.head(10)'
)

P1_VIZ = code(
    "overall_rate = df_churn['returned'].sum() / df_churn['cohort_size'].sum() * 100\n"
    '\n'
    'fig, ax = plt.subplots(figsize=(14, 10))\n'
    'ax.tick_params(axis="y", labelsize=11)  # smaller labels so all categories fit one page\n'
    "colors = ['#1565C0' if r > overall_rate else '#90CAF9'\n"
    "          for r in df_churn['return_rate_pct']]\n"
    "ax.barh(df_churn['category'], df_churn['return_rate_pct'], color=colors)\n"
    'ax.axvline(overall_rate, color="#E53935", linestyle="--", linewidth=1.5,\n'
    '           label=f"Platform avg: {overall_rate:.1f}%")\n'
    'ax.set_xlabel("Repeat Purchase Rate (%)")\n'
    'ax.set_title(\n'
    '    "Repeat Purchase Rate by First-Order Category\\n"\n'
    '    "(dark = above platform average  |  cohorts ≥ 50 customers)")\n'
    'ax.invert_yaxis()\n'
    'ax.legend()\n'
    'plt.tight_layout()\n'
    'plt.show()'
)

P2_HEADER = md(
    '---\n'
    '## 2. Revenue Opportunity Map: High-Revenue, Low-Churn Categories\n\n'
    '**Finding:** Overlaying revenue and repeat rate reveals the platform\'s growth opportunity.  \n'
    'Categories in the **top-right quadrant** (high revenue + above-average repeat rate) are '
    'where retention investment should be prioritised.'
)

P2_QUERY = code(
    'df_revenue = q(f"""\n'
    'SELECT\n'
    '    dp.product_category_name_english  AS category,\n'
    '    COUNT(DISTINCT fo.order_id)        AS order_count,\n'
    '    ROUND(SUM(fo.price), 0)            AS total_revenue\n'
    'FROM `{MARTS}.fact_orders` fo\n'
    'JOIN `{MARTS}.dim_products` dp ON fo.product_id = dp.product_id\n'
    "WHERE fo.order_status = 'delivered'\n"
    '  AND fo.order_id NOT IN ({EXCL_SQL})\n'
    '  AND dp.product_category_name_english IS NOT NULL\n'
    'GROUP BY category\n'
    'ORDER BY total_revenue DESC\n'
    '""")\n'
    '\n'
    "df_opp = df_revenue.merge(df_churn[['category', 'return_rate_pct', 'cohort_size']],\n"
    "                          on='category', how='inner')\n"
    'df_opp.head(10)'
)

P2_VIZ = code(
    'fig, ax = plt.subplots(figsize=(12, 7))\n'
    '\n'
    "ax.scatter(df_opp['total_revenue'], df_opp['return_rate_pct'],\n"
    "           s=df_opp['order_count'] / 3, alpha=0.65, color='#1565C0',\n"
    "           edgecolors='white', linewidths=0.5)\n"
    '\n'
    "median_revenue = df_opp['total_revenue'].median()\n"
    'ax.axhline(overall_rate, color="#E53935", linestyle="--", linewidth=1.2,\n'
    '           label=f"Avg repeat rate: {overall_rate:.1f}%")\n'
    'ax.axvline(median_revenue, color="#FB8C00", linestyle="--", linewidth=1.2,\n'
    '           label="Median revenue")\n'
    '\n'
    'top_right = df_opp[\n'
    "    (df_opp['total_revenue'] > median_revenue) &\n"
    "    (df_opp['return_rate_pct'] > overall_rate)\n"
    ']\n'
    'for _, row in top_right.iterrows():\n'
    '    cat = row["category"]\n'
    '    if cat == "bed_bath_table":\n'
    '        offset, arrow = (4, 35), dict(arrowstyle="-", color="grey", lw=1.8)\n'
    '    else:\n'
    '        offset, arrow = (6, 5), None\n'
    '    ax.annotate(cat, (row["total_revenue"], row["return_rate_pct"]),\n'
    '                fontsize=13, xytext=offset, textcoords="offset points",\n'
    '                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.6),\n'
    '                arrowprops=arrow)\n'
    '\n'
    'ax.set_xscale("log")\n'
    'ax.xaxis.set_major_formatter(\n'
    '    mticker.FuncFormatter(lambda x, _: f"R${x:,.0f}")\n'
    ')\n'
    'ax.set_xlabel("Total Revenue — BRL (log scale)")\n'
    'ax.set_ylabel("Repeat Purchase Rate (%)")\n'
    'ax.set_title("Revenue vs Repeat Rate by Category\\n"\n'
    '             "Top-right = high revenue AND high repeat  |  bubble size = order count")\n'
    'ax.legend()\n'
    'plt.tight_layout()\n'
    'plt.show()'
)

P3_HEADER = md(
    '---\n'
    '## 3. Geographic Seller Concentration\n\n'
    '**Finding:** Many Brazilian states outside São Paulo are severely underserved — '
    'high customer-to-seller ratios, slower delivery, and higher freight costs.  \n'
    'Recruiting local sellers in these states would reduce logistics costs and delivery time, '
    'directly improving buyer experience and repeat purchase potential.'
)

P3_QUERY = code(
    'df_geo = q(f"""\n'
    'WITH customer_counts AS (\n'
    '    SELECT state, COUNT(DISTINCT customer_unique_id) AS customers\n'
    '    FROM `{MARTS}.dim_customers`\n'
    '    GROUP BY state\n'
    '),\n'
    'seller_counts AS (\n'
    '    SELECT state, COUNT(DISTINCT seller_id) AS sellers\n'
    '    FROM `{MARTS}.dim_sellers`\n'
    '    GROUP BY state\n'
    '),\n'
    'delivery_stats AS (\n'
    '    SELECT\n'
    '        dc.state,\n'
    '        ROUND(AVG(fo.delivery_days), 1) AS avg_delivery_days,\n'
    '        ROUND(AVG(fo.freight_value), 2) AS avg_freight\n'
    '    FROM `{MARTS}.fact_orders` fo\n'
    '    JOIN `{MARTS}.dim_customers` dc ON fo.customer_id = dc.customer_id\n'
    "    WHERE fo.order_status = 'delivered'\n"
    '      AND fo.delivery_days IS NOT NULL\n'
    '      AND fo.order_id NOT IN ({EXCL_SQL})\n'
    '    GROUP BY dc.state\n'
    ')\n'
    'SELECT\n'
    '    c.state,\n'
    '    c.customers,\n'
    '    COALESCE(s.sellers, 0)                                     AS sellers,\n'
    '    ROUND(c.customers / NULLIF(COALESCE(s.sellers, 0), 0), 0) AS customer_per_seller,\n'
    '    d.avg_delivery_days,\n'
    '    d.avg_freight\n'
    'FROM customer_counts   c\n'
    'LEFT JOIN seller_counts  s ON c.state = s.state\n'
    'LEFT JOIN delivery_stats d ON c.state = d.state\n'
    'WHERE c.customers >= 100\n'
    'ORDER BY customer_per_seller DESC\n'
    '""")\n'
    'df_geo.head(10)'
)

P3_VIZ = code(
    "df_top = df_geo.sort_values('customer_per_seller', ascending=False).head(15)\n"
    '\n'
    'fig, axes = plt.subplots(1, 3, figsize=(16, 6))\n'
    '\n'
    "df_ratio = df_top.sort_values('customer_per_seller')\n"
    "axes[0].barh(df_ratio['state'], df_ratio['customer_per_seller'], color='#1565C0')\n"
    'axes[0].set_xlabel("Customers per Seller")\n'
    'axes[0].set_title("Customer-to-Seller Ratio\\n(most underserved states)")\n'
    '\n'
    "df_del = df_top.sort_values('avg_delivery_days')\n"
    "axes[1].barh(df_del['state'], df_del['avg_delivery_days'], color='#FB8C00')\n"
    'axes[1].set_xlabel("Avg Delivery Days")\n'
    'axes[1].set_title("Avg Delivery Time\\n(same states)")\n'
    '\n'
    "df_frg = df_top.sort_values('avg_freight')\n"
    "axes[2].barh(df_frg['state'], df_frg['avg_freight'], color='#E53935')\n"
    'axes[2].set_xlabel("Avg Freight (BRL)")\n'
    'axes[2].set_title("Avg Freight Cost\\n(same states)")\n'
    '\n'
    'plt.suptitle("Geographic Seller Concentration: Underserved States", y=1.01)\n'
    'plt.tight_layout()\n'
    'plt.show()'
)

P3_PAIRPLOT = code(
    '# Map Brazilian states to regions for colour coding\n'
    'REGION_MAP = {\n'
    "    'AM': 'Norte',  'PA': 'Norte',  'AC': 'Norte',  'RO': 'Norte',\n"
    "    'RR': 'Norte',  'AP': 'Norte',  'TO': 'Norte',\n"
    "    'MA': 'Nordeste', 'PI': 'Nordeste', 'CE': 'Nordeste', 'RN': 'Nordeste',\n"
    "    'PB': 'Nordeste', 'PE': 'Nordeste', 'AL': 'Nordeste', 'SE': 'Nordeste', 'BA': 'Nordeste',\n"
    "    'MT': 'Centro-Oeste', 'MS': 'Centro-Oeste', 'GO': 'Centro-Oeste', 'DF': 'Centro-Oeste',\n"
    "    'SP': 'Sudeste',  'RJ': 'Sudeste',  'MG': 'Sudeste',  'ES': 'Sudeste',\n"
    "    'PR': 'Sul',      'SC': 'Sul',      'RS': 'Sul'\n"
    '}\n'
    "df_geo['region'] = df_geo['state'].map(REGION_MAP)\n"
    '\n'
    "pair_cols = ['customers', 'sellers', 'customer_per_seller',\n"
    "             'avg_delivery_days', 'avg_freight']\n"
    '\n'
    'g = sns.pairplot(\n'
    "    df_geo[pair_cols + ['region']].dropna(),\n"
    "    hue='region',\n"
    "    palette='tab10',\n"
    "    diag_kind='kde',\n"
    "    plot_kws={'alpha': 0.75, 's': 80},\n"
    "    diag_kws={'linewidth': 1.5}\n"
    ')\n'
    'g.figure.suptitle(\n'
    "    'Geographic Seller Concentration — Multi-dimensional View\\n'\n"
    "    '(coloured by Brazilian region)',\n"
    '    y=1.02\n'
    ')\n'
    '# moderate spacing between subplots + room for suptitle\n'
    'g.figure.subplots_adjust(top=0.88, hspace=0.15, wspace=0.15)\n'
    '# horizontal y-axis labels with padding so they clear the tick marks\n'
    'for ax in g.axes.flatten():\n'
    '    if ax is not None:\n'
    '        ax.yaxis.label.set_rotation(0)\n'
    '        ax.yaxis.label.set_ha("right")\n'
    '        ax.yaxis.label.set_va("center")\n'
    '        ax.yaxis.labelpad = 35\n'
    '        ax.xaxis.labelpad = 10\n'
    'plt.show()'
)

P3B_HEADER = md(
    '### 3b. Focused View — The Logistics Penalty of Under-Supply\n\n'
    'The pairplot above captures all pairwise relationships for exploration. '
    'This panel isolates the **primary argument**: states with fewer sellers per customer '
    'pay more *and* wait longer for their orders.\n\n'
    'A positive trend line in both panels confirms the pattern. '
    '**Norte and Nordeste** states cluster toward the top-right — they are the priority '
    'targets for seller recruitment. Closing the supply gap there would reduce freight '
    'costs and delivery times, directly improving customer experience and repeat rates '
    'in the regions Olist currently serves least well.'
)

P3B_VIZ = code(
    'import numpy as np\n'
    'from matplotlib.lines import Line2D\n'
    '\n'
    "_region_order = ['Norte', 'Nordeste', 'Centro-Oeste', 'Sudeste', 'Sul']\n"
    '_p3b_pal = dict(zip(_region_order, sns.color_palette("tab10", len(_region_order))))\n'
    '\n'
    "df_s = df_geo.dropna(subset=['customer_per_seller', 'avg_freight', 'avg_delivery_days', 'region'])\n"
    '\n'
    'def _p3b_panel(ax, y_col, y_label):\n'
    '    for region, grp in df_s.groupby("region"):\n'
    '        ax.scatter(grp["customer_per_seller"], grp[y_col],\n'
    '                   color=_p3b_pal[region], s=80, alpha=0.85,\n'
    '                   edgecolors="white", linewidths=0.5, zorder=3)\n'
    '        for _, row in grp.iterrows():\n'
    '            ax.annotate(row["state"],\n'
    '                        (row["customer_per_seller"], row[y_col]),\n'
    '                        fontsize=8, xytext=(5, 3), textcoords="offset points")\n'
    '    x = df_s["customer_per_seller"].astype(float).values\n'
    '    y = df_s[y_col].astype(float).values\n'
    '    m, b = np.polyfit(x, y, 1)\n'
    '    x_line = np.linspace(x.min(), x.max(), 100)\n'
    '    ax.plot(x_line, m * x_line + b, color="grey", linestyle="--", linewidth=1.5)\n'
    '    ax.set_xlabel("Customers per Seller")\n'
    '    ax.set_ylabel(y_label)\n'
    '    ax.margins(x=0.12)\n'
    '    handles = [\n'
    '        Line2D([0], [0], marker="o", color="w",\n'
    '               markerfacecolor=_p3b_pal[r], markeredgecolor="white",\n'
    '               markersize=9, label=r)\n'
    '        for r in _region_order if r in df_s["region"].values\n'
    '    ]\n'
    '    handles.append(Line2D([0], [0], color="grey", linestyle="--",\n'
    '                          linewidth=1.5, label=f"Trend (slope={m:.2f})"))\n'
    '    ax.legend(handles=handles, loc="lower right")\n'
    '\n'
    'fig, axes = plt.subplots(1, 2, figsize=(16, 7))\n'
    '\n'
    '_p3b_panel(axes[0], "avg_freight",       "Avg Freight (BRL)")\n'
    'axes[0].set_title("Underserved states pay more\\n(customer/seller ratio vs freight cost)")\n'
    '\n'
    '_p3b_panel(axes[1], "avg_delivery_days", "Avg Delivery Days")\n'
    'axes[1].set_title("Underserved states wait longer\\n(customer/seller ratio vs delivery time)")\n'
    '\n'
    'plt.suptitle(\n'
    '    "Seller Gap → Logistics Gap: The Case for Regional Seller Recruitment",\n'
    '    y=1.02\n'
    ')\n'
    'plt.tight_layout()\n'
    'plt.show()'
)

P4_HEADER = md(
    '---\n'
    '## 4. Seller Health Monitoring\n\n'
    '**Finding:** 18% of sellers made exactly one sale and disappeared. '
    'Olist currently has no mechanism to detect declining sellers before they churn, '
    'threatening supply diversity.\n\n'
    '**Our pipeline\'s contribution:** `snap_dim_sellers` (SCD Type 2 snapshot on `stg_sellers`) '
    'gives Olist the infrastructure to track seller changes over time — including address '
    'changes that may correlate with shifts in delivery performance. '
    'Combined with the monthly health metrics below, this enables an early-warning system '
    'to intervene before a seller goes dark.'
)

P4_DIST = code(
    'df_seller_dist = q(f"""\n'
    'WITH seller_orders AS (\n'
    '    SELECT seller_id, COUNT(DISTINCT order_id) AS order_count\n'
    '    FROM `{MARTS}.fact_orders`\n'
    "    WHERE order_status = 'delivered'\n"
    '    GROUP BY seller_id\n'
    ')\n'
    'SELECT\n'
    "    CASE\n"
    "        WHEN order_count = 1              THEN '1 (one-and-done)'\n"
    "        WHEN order_count BETWEEN 2 AND 5  THEN '2–5'\n"
    "        WHEN order_count BETWEEN 6 AND 20 THEN '6–20'\n"
    "        ELSE '21+'\n"
    '    END                                                        AS sales_bucket,\n'
    '    COUNT(*)                                                   AS seller_count,\n'
    '    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1)        AS pct\n'
    'FROM seller_orders\n'
    'GROUP BY sales_bucket\n'
    'ORDER BY MIN(order_count)\n'
    '""")\n'
    'print(df_seller_dist.to_string(index=False))'
)

P4_MONTHLY = code(
    'df_monthly = q(f"""\n'
    'SELECT\n'
    '    DATE_TRUNC(DATE(fo.order_purchase_timestamp), MONTH) AS month,\n'
    '    COUNT(DISTINCT fo.seller_id)                          AS active_sellers,\n'
    '    ROUND(AVG(fr.review_score), 2)                        AS avg_review_score,\n'
    '    ROUND(COUNTIF(fo.is_late) / COUNT(*) * 100, 1)        AS late_delivery_pct\n'
    'FROM `{MARTS}.fact_orders` fo\n'
    'LEFT JOIN `{MARTS}.fact_reviews` fr\n'
    '    ON fo.order_id = fr.order_id\n'
    '    AND DATE(fr.review_creation_date) >= DATE(fo.order_purchase_timestamp)  -- exclude 74 anomalous reviews\n'
    "WHERE fo.order_status = 'delivered'\n"
    '  AND fo.order_id NOT IN ({EXCL_SQL})\n'
    'GROUP BY month\n'
    'ORDER BY month\n'
    '""")\n'
    "df_monthly['month'] = pd.to_datetime(df_monthly['month'])\n"
    'df_monthly.head()'
)

P4_VIZ = code(
    'fig, axes = plt.subplots(1, 2, figsize=(15, 7))\n'
    '\n'
    "bar_colors = ['#E53935', '#FB8C00', '#1565C0', '#2E7D32']\n"
    "bars = axes[0].bar(df_seller_dist['sales_bucket'],\n"
    "                   df_seller_dist['seller_count'], color=bar_colors)\n"
    'for bar, pct in zip(bars, df_seller_dist["pct"]):\n'
    '    axes[0].text(bar.get_x() + bar.get_width() / 2,\n'
    '                 bar.get_height() + 10,\n'
    '                 f"{pct}%", ha="center", va="bottom", fontsize=9)\n'
    'axes[0].set_xlabel("Delivered Orders per Seller")\n'
    'axes[0].set_ylabel("Number of Sellers")\n'
    'axes[0].set_title("Seller Distribution by Total Delivered Orders")\n'
    '\n'
    'ax_r = axes[1].twinx()\n'
    "axes[1].plot(df_monthly['month'], df_monthly['active_sellers'],\n"
    "             color='#1565C0', linewidth=2, label='Active sellers')\n"
    "ax_r.plot(df_monthly['month'], df_monthly['avg_review_score'],\n"
    "          color='#2E7D32', linewidth=2, linestyle='--', label='Avg review score')\n"
    "ax_r.plot(df_monthly['month'], df_monthly['late_delivery_pct'],\n"
    "          color='#E53935', linewidth=1.5, linestyle=':', label='Late delivery %')\n"
    '\n'
    'axes[1].set_xlabel("Month")\n'
    'axes[1].set_ylabel("Active Sellers")\n'
    'ax_r.set_ylabel("Score / %", color="#555")\n'
    'axes[1].set_title("Monthly Seller Ecosystem Health")\n'
    'plt.setp(axes[1].xaxis.get_majorticklabels(), rotation=45, ha="right")\n'
    '\n'
    'lines1, labels1 = axes[1].get_legend_handles_labels()\n'
    'lines2, labels2 = ax_r.get_legend_handles_labels()\n'
    'axes[1].legend(lines1 + lines2, labels1 + labels2, loc="upper left")\n'
    '\n'
    'plt.suptitle(\n'
    '    "Seller Health Monitoring\\n"\n'
    '    "snap_dim_sellers enables correlation of address changes with performance shifts",\n'
    '    y=1.02\n'
    ')\n'
    'plt.tight_layout()\n'
    'plt.show()'
)

P5_HEADER = md(
    '---\n'
    '## 5. Delivery Failure vs Customer Churn — Regional View\n\n'
    '**Question:** Do late delivery or high freight cost on the first order predict whether '
    'a customer will return?  \n'
    '**Method:** For each customer, capture their first delivered order\'s `is_late` flag and '
    '`freight_value`, then check if they ever returned (`total_orders > 1`). '
    'Aggregate by state and compare both factors against churn rate side-by-side.\n\n'
    '**Interpretation:** A flat trend line (near-zero slope) in both charts would support '
    'Point 1\'s finding that bad experience factors do not drive churn — product category '
    'remains the dominant driver.  \n'
    'Regional clustering reveals whether Norte/Nordeste states (high freight, slow delivery) '
    'show systematically different churn behaviour from Sudeste/Sul.'
)

P5_QUERY = code(
    'df_dc = q(f"""\n'
    'WITH customer_first_order AS (\n'
    '    SELECT\n'
    '        dc.customer_unique_id,\n'
    '        dc.state,\n'
    '        fo.is_late,\n'
    '        fo.freight_value,\n'
    '        ROW_NUMBER() OVER (\n'
    '            PARTITION BY dc.customer_unique_id\n'
    '            ORDER BY fo.order_purchase_timestamp\n'
    '        ) AS rn\n'
    '    FROM `{MARTS}.fact_orders` fo\n'
    '    JOIN `{MARTS}.dim_customers` dc ON fo.customer_id = dc.customer_id\n'
    "    WHERE fo.order_status = 'delivered'\n"
    '      AND fo.order_id NOT IN ({EXCL_SQL})\n'
    '),\n'
    'first_orders AS (\n'
    '    SELECT customer_unique_id, state, is_late, freight_value\n'
    '    FROM customer_first_order\n'
    '    WHERE rn = 1\n'
    ')\n'
    'SELECT\n'
    '    fo.state,\n'
    '    COUNT(*)                                                    AS customers,\n'
    '    ROUND(COUNTIF(fo.is_late) / COUNT(*) * 100, 1)             AS late_rate_pct,\n'
    '    ROUND(AVG(fo.freight_value), 2)                            AS avg_freight_first_order,\n'
    '    ROUND(COUNTIF(mcs.total_orders = 1) / COUNT(*) * 100, 1)   AS churn_rate_pct\n'
    'FROM first_orders fo\n'
    'JOIN `{MARTS}.mart_customer_summary` mcs\n'
    '    ON fo.customer_unique_id = mcs.customer_unique_id\n'
    'GROUP BY fo.state\n'
    'HAVING COUNT(*) >= 100\n'
    'ORDER BY late_rate_pct DESC\n'
    '""")\n'
    "df_dc['region'] = df_dc['state'].map(REGION_MAP)\n"
    '\n'
    "region_order = ['Norte', 'Nordeste', 'Centro-Oeste', 'Sudeste', 'Sul']\n"
    'p5_palette = dict(zip(region_order, sns.color_palette("tab10", len(region_order))))\n'
    'df_dc'
)

P5_VIZ = code(
    'import numpy as np\n'
    'from matplotlib.lines import Line2D\n'
    '\n'
    'def scatter_churn(ax, x_col, x_label):\n'
    '    for region, grp in df_dc.groupby("region"):\n'
    '        ax.scatter(\n'
    '            grp[x_col], grp["churn_rate_pct"],\n'
    '            s=grp["customers"] / 10,\n'
    '            color=p5_palette[region], alpha=0.8,\n'
    '            edgecolors="white", linewidths=0.6\n'
    '        )\n'
    '        for _, row in grp.iterrows():\n'
    '            ax.annotate(\n'
    '                row["state"],\n'
    '                (row[x_col], row["churn_rate_pct"]),\n'
    '                fontsize=8, xytext=(5, 3), textcoords="offset points"\n'
    '            )\n'
    '    x = df_dc[x_col].astype(float).values\n'
    '    y = df_dc["churn_rate_pct"].astype(float).values\n'
    '    m, b = np.polyfit(x, y, 1)\n'
    '    x_line = np.linspace(x.min(), x.max(), 100)\n'
    '    ax.plot(x_line, m * x_line + b, color="grey", linestyle="--", linewidth=1.5)\n'
    '    # uniform-size legend handles\n'
    '    handles = [\n'
    '        Line2D([0], [0], marker="o", color="w",\n'
    '               markerfacecolor=p5_palette[r], markeredgecolor="white",\n'
    '               markersize=9, label=r)\n'
    '        for r in region_order\n'
    '    ]\n'
    '    handles.append(Line2D([0], [0], color="grey", linestyle="--",\n'
    '                           linewidth=1.5, label=f"Trend (slope = {m:.2f})"))\n'
    '    ax.margins(x=0.15)\n'
    '    ax.set_ylabel("Customer Churn Rate (%)")\n'
    '    ax.set_xlabel(x_label)\n'
    '    ax.legend(handles=handles, loc="lower right")\n'
    '    return m\n'
    '\n'
    'fig, axes = plt.subplots(1, 2, figsize=(18, 7))\n'
    '\n'
    'm_late = scatter_churn(axes[0], "late_rate_pct", "Late Delivery Rate on First Order (%)")\n'
    'axes[0].set_title("Late Delivery Rate vs Churn\\n(by state, coloured by region)")\n'
    '\n'
    'm_freight = scatter_churn(axes[1], "avg_freight_first_order", "Avg Freight on First Order (BRL)")\n'
    'axes[1].set_title("Freight Cost vs Churn\\n(by state, coloured by region)")\n'
    '\n'
    'plt.suptitle(\n'
    '    "Delivery Failure & Freight Cost vs Customer Churn — Regional View\\n"\n'
    '    "(bubble size = customer count)",\n'
    '    y=1.02\n'
    ')\n'
    'plt.tight_layout()\n'
    'plt.show()\n'
    '\n'
    'for label, m in [("Late delivery rate", m_late), ("Avg freight cost", m_freight)]:\n'
    '    strength = "weak/no" if abs(m) < 0.1 else "meaningful"\n'
    '    print(f"{label}: slope = {m:.3f}  →  {strength} correlation with churn")'
)

P6_HEADER = md(
    '---\n'
    '## 6. Cohort Retention — When Buyers Disengage\n\n'
    '**What this tells us:** Each row is a group of customers who made their first purchase '
    'in the same month (their cohort). Each column shows what percentage of that cohort '
    'placed another order N months later.  \n'
    'Month 0 is always 100% — that\'s the acquisition month itself.\n\n'
    '**Why it matters for campaigns:** The heatmap reveals the exact moment retention '
    'collapses. If month 2 drops sharply, that\'s the intervention window — a well-timed '
    'campaign at month 1–2 post-purchase could recover a significant share of the 97% who '
    'never return.\n\n'
    '**Automation:** `mart_cohort_retention` refreshes with every `dbt run`. '
    'A Dagster job can email the updated heatmap to the marketing team on a weekly cadence.'
)

P6_QUERY = code(
    'df_cohort = q(f"""\n'
    'SELECT cohort_month, months_since_first, retention_rate_pct\n'
    'FROM `{MARTS}.mart_cohort_retention`\n'
    'ORDER BY cohort_month, months_since_first\n'
    '""")\n'
    "df_cohort['cohort_month'] = pd.to_datetime(df_cohort['cohort_month']).dt.strftime('%Y-%m')\n"
    'df_cohort.head(10)'
)

P6_VIZ = code(
    'pivot = df_cohort.pivot(\n'
    '    index="cohort_month", columns="months_since_first", values="retention_rate_pct"\n'
    ')\n'
    '\n'
    'fig, ax = plt.subplots(figsize=(18, 9))\n'
    'sns.heatmap(\n'
    '    pivot,\n'
    '    annot=True, fmt=".0f",\n'
    '    cmap="Blues",\n'
    '    linewidths=0.3, linecolor="white",\n'
    '    cbar_kws={"label": "Retention Rate (%)"},\n'
    '    ax=ax\n'
    ')\n'
    'ax.set_title(\n'
    '    "Customer Cohort Retention Heatmap\\n"\n'
    '    "(% of cohort still active at month N  |  month 0 = acquisition month)"\n'
    ')\n'
    'ax.set_xlabel("Months Since First Order")\n'
    'ax.set_ylabel("Acquisition Cohort")\n'
    'plt.tight_layout()\n'
    'plt.show()\n'
    '\n'
    '# Identify the sharpest drop — the primary intervention window\n'
    'month1 = pivot[1].mean() if 1 in pivot.columns else None\n'
    'month2 = pivot[2].mean() if 2 in pivot.columns else None\n'
    'if month1 and month2:\n'
    '    print(f"Avg retention  month 1: {month1:.1f}%")\n'
    '    print(f"Avg retention  month 2: {month2:.1f}%")\n'
    '    print(f"Drop month 1→2: {month1 - month2:.1f} pp — '\
        'primary campaign intervention window")'
)

P7_HEADER = md(
    '---\n'
    '## 7. RFM Segmentation — Who to Target\n\n'
    '**What this tells us:** Every customer is scored 1–5 on Recency, Frequency, and '
    'Monetary value, then assigned to a segment that prescribes the right campaign action.\n\n'
    '| Segment | Description | Recommended action |\n'
    '|---|---|---|\n'
    '| **champions** | Bought recently, often, and spent the most | Reward — loyalty perks, early access |\n'
    '| **loyal_customers** | Buy regularly, respond to promotions | Upsell — bundles, cross-category offers |\n'
    '| **promising** | Recent but infrequent — still exploring | Nurture — personalised recommendations |\n'
    '| **potential_loyalists** | Above-average recency, not yet frequent | Engage — second-purchase incentive |\n'
    '| **at_risk** | Used to buy often but haven\'t recently | Win-back — time-sensitive discount |\n'
    '| **lost** | Infrequent, long ago | Reactivation — high-value offer or sunset |\n\n'
    '**Automation:** `mart_rfm_scores` re-segments every customer on each `dbt run`. '
    'Dagster can push the at_risk and lost lists directly to the CRM for campaign triggering.'
)

P7_QUERY = code(
    'df_rfm_seg = q(f"""\n'
    'SELECT\n'
    '    rfm_segment,\n'
    '    COUNT(*)                       AS customers,\n'
    '    ROUND(AVG(rfm_score), 2)       AS avg_rfm_score,\n'
    '    ROUND(AVG(monetary), 2)        AS avg_monetary,\n'
    '    ROUND(AVG(recency_days), 0)    AS avg_recency_days\n'
    'FROM `{MARTS}.mart_rfm_scores`\n'
    'GROUP BY rfm_segment\n'
    'ORDER BY avg_rfm_score DESC\n'
    '""")\n'
    'df_rfm_seg'
)

P7_VIZ = code(
    'SEG_COLORS = {\n'
    '    "champions":          "#1B5E20",\n'
    '    "loyal_customers":    "#2E7D32",\n'
    '    "promising":          "#66BB6A",\n'
    '    "potential_loyalists":"#FB8C00",\n'
    '    "at_risk":            "#E64A19",\n'
    '    "lost":               "#B71C1C",\n'
    '}\n'
    '\n'
    'fig, axes = plt.subplots(1, 2, figsize=(16, 6))\n'
    '\n'
    '# Left: customer count per segment\n'
    'colors = [SEG_COLORS.get(s, "#90A4AE") for s in df_rfm_seg["rfm_segment"]]\n'
    'bars = axes[0].barh(df_rfm_seg["rfm_segment"], df_rfm_seg["customers"], color=colors)\n'
    'for bar, n in zip(bars, df_rfm_seg["customers"]):\n'
    '    axes[0].text(bar.get_width() + 200, bar.get_y() + bar.get_height() / 2,\n'
    '                 f"{n:,}", va="center", fontsize=9)\n'
    'axes[0].set_xlabel("Number of Customers")\n'
    'axes[0].set_title("Customer Count by RFM Segment\\n(ordered by avg RFM score)")\n'
    'axes[0].invert_yaxis()\n'
    '\n'
    '# Right: avg monetary value per segment — shows revenue potential\n'
    'bars2 = axes[1].barh(df_rfm_seg["rfm_segment"], df_rfm_seg["avg_monetary"], color=colors)\n'
    'for bar, v in zip(bars2, df_rfm_seg["avg_monetary"]):\n'
    '    axes[1].text(bar.get_width() + 5, bar.get_y() + bar.get_height() / 2,\n'
    '                 f"R${v:,.0f}", va="center", fontsize=9)\n'
    'axes[1].set_xlabel("Avg Customer Spend (BRL)")\n'
    'axes[1].set_title("Avg Monetary Value by Segment\\n(size of win-back prize)")\n'
    'axes[1].invert_yaxis()\n'
    '\n'
    'plt.suptitle("RFM Segmentation — Campaign Targeting Map", y=1.01)\n'
    'plt.tight_layout()\n'
    'plt.show()\n'
    '\n'
    'actionable = df_rfm_seg[df_rfm_seg["rfm_segment"].isin(["at_risk", "lost"])]\n'
    'total_actionable = actionable["customers"].sum()\n'
    'print(f"\\nAt-risk + lost customers: {total_actionable:,} "\n'
    '      f"({total_actionable / df_rfm_seg[\'customers\'].sum() * 100:.1f}% of base) "\n'
    '      f"— primary win-back campaign targets")'
)

P8_HEADER = md(
    '---\n'
    '## 8. Seller Health Dashboard\n\n'
    '**What this tells us:** Each seller receives a composite health score (0–100) based on '
    'customer review scores (40%), on-time delivery rate (35%), and overall delivery rate (25%). '
    'A 90-day recent window is compared against the all-time baseline to surface trend signals.\n\n'
    '**Trend status:**\n'
    '- `stable` — recent performance in line with historical baseline\n'
    '- `declining` — recent score dropped >10 points vs baseline (needs intervention)\n'
    '- `inactive` — no orders in the past 90 days (churn risk or already gone)\n\n'
    '**Automation:** `mart_seller_health` recomputes on every daily `dbt run`. '
    'Dagster can query `WHERE trend_status != \'stable\'` and push alerts to the '
    'seller success team before a seller fully churns — closing the visibility gap '
    'that currently lets 18% of sellers disappear after a single sale.'
)

P8_QUERY = code(
    'df_health = q(f"""\n'
    'SELECT seller_id, total_orders, health_score, health_tier,\n'
    '       recent_total_orders, recent_health_score, score_delta, trend_status\n'
    'FROM `{MARTS}.mart_seller_health`\n'
    '""")\n'
    '\n'
    'df_tier = q(f"""\n'
    'SELECT\n'
    '    health_tier,\n'
    '    trend_status,\n'
    '    COUNT(*)                           AS sellers,\n'
    '    ROUND(AVG(health_score), 1)        AS avg_score,\n'
    '    ROUND(AVG(total_orders), 1)        AS avg_orders\n'
    'FROM `{MARTS}.mart_seller_health`\n'
    'GROUP BY health_tier, trend_status\n'
    'ORDER BY avg_score DESC, trend_status\n'
    '""")\n'
    'df_tier'
)

P8_VIZ = code(
    'TIER_COLORS = {\n'
    '    "excellent": "#1B5E20",\n'
    '    "good":      "#FB8C00",\n'
    '    "at_risk":   "#E64A19",\n'
    '    "critical":  "#B71C1C",\n'
    '}\n'
    'TREND_COLORS = {\n'
    '    "stable":   "#1565C0",\n'
    '    "declining":"#E53935",\n'
    '    "inactive": "#9E9E9E",\n'
    '}\n'
    '\n'
    'fig, axes = plt.subplots(1, 3, figsize=(18, 6))\n'
    '\n'
    '# Left: health score distribution\n'
    'axes[0].hist(df_health["health_score"].dropna(), bins=20,\n'
    '             color="#1565C0", edgecolor="white", linewidth=0.5)\n'
    'axes[0].set_xlabel("Health Score (0–100)")\n'
    'axes[0].set_ylabel("Number of Sellers")\n'
    'axes[0].set_title("Seller Health Score Distribution")\n'
    'for thresh, label, color in [(80,"excellent","#1B5E20"),(60,"good","#FB8C00"),\n'
    '                              (40,"at_risk","#E64A19")]:\n'
    '    axes[0].axvline(thresh, color=color, linestyle="--", linewidth=1.2, label=label)\n'
    'axes[0].legend()\n'
    '\n'
    '# Centre: tier breakdown\n'
    'tier_counts = df_health["health_tier"].value_counts().reindex(\n'
    '    ["excellent", "good", "at_risk", "critical"]\n'
    ')\n'
    'axes[1].bar(tier_counts.index, tier_counts.values,\n'
    '            color=[TIER_COLORS[t] for t in tier_counts.index])\n'
    'for i, (tier, cnt) in enumerate(tier_counts.items()):\n'
    '    axes[1].text(i, cnt + 5, f"{cnt:,}", ha="center", fontsize=9)\n'
    'axes[1].set_xlabel("Health Tier")\n'
    'axes[1].set_ylabel("Number of Sellers")\n'
    'axes[1].set_title("Sellers by Health Tier")\n'
    '\n'
    '# Right: trend status breakdown\n'
    'trend_counts = df_health["trend_status"].value_counts().reindex(\n'
    '    ["stable", "declining", "inactive"]\n'
    ')\n'
    'axes[2].bar(trend_counts.index, trend_counts.values,\n'
    '            color=[TREND_COLORS[t] for t in trend_counts.index])\n'
    'for i, (trend, cnt) in enumerate(trend_counts.items()):\n'
    '    axes[2].text(i, cnt + 5, f"{cnt:,}", ha="center", fontsize=9)\n'
    'axes[2].set_xlabel("Trend Status")\n'
    'axes[2].set_ylabel("Number of Sellers")\n'
    'axes[2].set_title("Seller Trend Status\\n(declining + inactive = action needed)")\n'
    '\n'
    'plt.suptitle("Seller Health Dashboard", y=1.01)\n'
    'plt.tight_layout()\n'
    'plt.show()\n'
    '\n'
    'alert_count = (df_health["trend_status"] != "stable").sum()\n'
    'print(f"\\nSellers needing intervention: {alert_count:,} "\n'
    '      f"({alert_count / len(df_health) * 100:.1f}% of seller base)")\n'
    'print("\\nTop 10 declining sellers (for outreach):")\n'
    'print(\n'
    '    df_health[df_health["trend_status"] == "declining"]\n'
    '    .sort_values("score_delta")\n'
    '    .head(10)[["seller_id", "health_score", "recent_health_score", "score_delta", "total_orders"]]\n'
    '    .to_string(index=False)\n'
    ')'
)

# ── Assemble & write ──────────────────────────────────────────────────────────

notebook = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3 (ipykernel)",
            "language": "python",
            "name": "python3"
        },
        "language_info": {"name": "python", "version": "3.11.14"}
    },
    "cells": [
        TITLE, SETUP,
        DQ_HEADER, DQ_CODE,
        P1_HEADER, P1_QUERY, P1_VIZ,
        P2_HEADER, P2_QUERY, P2_VIZ,
        P3_HEADER, P3_QUERY, P3_VIZ, P3_PAIRPLOT, P3B_HEADER, P3B_VIZ,
        P4_HEADER, P4_DIST, P4_MONTHLY, P4_VIZ,
        P5_HEADER, P5_QUERY, P5_VIZ,
        P6_HEADER, P6_QUERY, P6_VIZ,
        P7_HEADER, P7_QUERY, P7_VIZ,
        P8_HEADER, P8_QUERY, P8_VIZ,
    ]
}

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)

print(f'Notebook written to {OUT}')
