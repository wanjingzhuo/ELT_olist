#!/usr/bin/env python3
"""
Olist E-Commerce Intelligence Dashboard v2
Fetches from BigQuery mart tables → self-contained HTML → docs/index.html

Run:    python report/generate_dashboard.py
Deploy: git add docs/index.html && git commit -m "..." && git push
Live:   https://maycoooz.github.io/ELT_olist/
"""
import json, pathlib, decimal, datetime
import pandas as pd
from google.cloud import bigquery

# ── Config ─────────────────────────────────────────────────────────────────────
KEY_FILE = '/Users/tess/NTU/M2/Project/olist-498903-e7f8763e517a.json'
PROJECT  = 'olist-498903'
DATASET  = 'olist_transformed'
MARTS    = f'{PROJECT}.{DATASET}_marts'
EXCL     = "'bfbd0f9bdef84302105ad712db648a6c'"
OUT      = pathlib.Path(__file__).parent.parent / 'docs' / 'index.html'

client = bigquery.Client.from_service_account_json(KEY_FILE)
q = lambda sql: client.query(sql).to_dataframe()

# ── Brazil state metadata ───────────────────────────────────────────────────────
STATE_COORDS = {
    'AC':[-9.02,-70.81],'AL':[-9.57,-36.78],'AM':[-4.00,-61.99],
    'AP':[0.90,-52.00], 'BA':[-12.57,-41.70],'CE':[-5.50,-39.32],
    'DF':[-15.78,-47.93],'ES':[-19.19,-40.34],'GO':[-15.83,-49.98],
    'MA':[-4.96,-45.27],'MG':[-18.10,-44.38],'MS':[-20.51,-54.54],
    'MT':[-12.64,-55.42],'PA':[-3.79,-52.48],'PB':[-7.06,-36.55],
    'PE':[-8.81,-36.95],'PI':[-7.72,-42.73],'PR':[-24.89,-51.55],
    'RJ':[-22.25,-42.66],'RN':[-5.84,-36.53],'RO':[-10.83,-63.34],
    'RR':[2.07,-61.40], 'RS':[-30.03,-53.23],'SC':[-27.45,-50.95],
    'SE':[-10.57,-37.45],'SP':[-22.19,-48.79],'TO':[-10.18,-48.33],
}
STATE_NAMES = {
    'AC':'Acre','AL':'Alagoas','AM':'Amazonas','AP':'Amapá','BA':'Bahia',
    'CE':'Ceará','DF':'Distrito Federal','ES':'Espírito Santo','GO':'Goiás',
    'MA':'Maranhão','MG':'Minas Gerais','MS':'Mato Grosso do Sul',
    'MT':'Mato Grosso','PA':'Pará','PB':'Paraíba','PE':'Pernambuco',
    'PI':'Piauí','PR':'Paraná','RJ':'Rio de Janeiro','RN':'Rio Grande do Norte',
    'RO':'Rondônia','RR':'Roraima','RS':'Rio Grande do Sul',
    'SC':'Santa Catarina','SE':'Sergipe','SP':'São Paulo','TO':'Tocantins',
}


class BQEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal): return float(obj)
        if isinstance(obj, (datetime.date, datetime.datetime)): return str(obj)
        if hasattr(obj, 'item'): return obj.item()
        return super().default(obj)


# ── BigQuery fetches ────────────────────────────────────────────────────────────
def fetch():
    print('Fetching from BigQuery…')

    kpi = q(f"""
        SELECT
            COUNT(DISTINCT fo.order_id)                              AS total_orders,
            COUNT(DISTINCT dc.customer_unique_id)                    AS unique_customers,
            ROUND(SUM(fo.price), 0)                                  AS total_revenue,
            ROUND(AVG(fo.price), 2)                                  AS avg_order_value,
            ROUND(COUNTIF(fo.is_late) / COUNT(*) * 100, 1)           AS late_pct,
            ROUND(AVG(fr.review_score), 2)                           AS avg_review_score
        FROM `{MARTS}.fact_orders` fo
        JOIN `{MARTS}.dim_customers` dc ON fo.customer_id = dc.customer_id
        LEFT JOIN `{MARTS}.fact_reviews` fr ON fo.order_id = fr.order_id
            AND DATE(fr.review_creation_date) >= DATE(fo.order_purchase_timestamp)
        WHERE fo.order_status = 'delivered'
          AND fo.order_id NOT IN ({EXCL})
    """).iloc[0]

    repeat_pct = q(f"""
        SELECT ROUND(COUNTIF(total_orders > 1) / COUNT(*) * 100, 1) AS v
        FROM `{MARTS}.mart_customer_summary`
    """).iloc[0]['v']

    geo = q(f"""
        WITH cc AS (
            SELECT state, COUNT(DISTINCT customer_unique_id) AS customers
            FROM `{MARTS}.dim_customers` GROUP BY state
        ),
        sc AS (
            SELECT state, COUNT(DISTINCT seller_id) AS sellers
            FROM `{MARTS}.dim_sellers` GROUP BY state
        ),
        ds AS (
            SELECT dc.state,
                ROUND(AVG(fo.delivery_days), 1)             AS avg_delivery_days,
                ROUND(AVG(fo.freight_value), 2)             AS avg_freight,
                ROUND(COUNTIF(fo.is_late)/COUNT(*)*100, 1)  AS late_pct
            FROM `{MARTS}.fact_orders` fo
            JOIN `{MARTS}.dim_customers` dc ON fo.customer_id = dc.customer_id
            WHERE fo.order_status = 'delivered'
              AND fo.delivery_days IS NOT NULL
              AND fo.order_id NOT IN ({EXCL})
            GROUP BY dc.state
        ),
        hs AS (
            SELECT d.state, ROUND(AVG(h.health_score), 1) AS avg_health_score
            FROM `{MARTS}.mart_seller_health` h
            JOIN `{MARTS}.dim_sellers` d ON h.seller_id = d.seller_id
            GROUP BY d.state
        ),
        ch AS (
            SELECT state,
                ROUND(COUNTIF(total_orders = 1)/COUNT(*)*100, 1) AS churn_rate_pct
            FROM `{MARTS}.mart_customer_summary`
            GROUP BY state
        )
        SELECT cc.state, cc.customers,
            COALESCE(sc.sellers, 0) AS sellers,
            ROUND(cc.customers / NULLIF(COALESCE(sc.sellers,0), 0), 0) AS customer_per_seller,
            ds.avg_delivery_days, ds.avg_freight, ds.late_pct,
            hs.avg_health_score, ch.churn_rate_pct
        FROM cc
        LEFT JOIN sc USING (state)
        LEFT JOIN ds USING (state)
        LEFT JOIN hs USING (state)
        LEFT JOIN ch USING (state)
        WHERE cc.customers >= 100
        ORDER BY cc.customers DESC
    """)
    geo['lat'] = geo['state'].map(lambda s: STATE_COORDS.get(s, [0, 0])[0])
    geo['lng'] = geo['state'].map(lambda s: STATE_COORDS.get(s, [0, 0])[1])
    geo['name'] = geo['state'].map(STATE_NAMES).fillna(geo['state'])

    monthly = q(f"""
        SELECT
            FORMAT_DATE('%Y-%m', DATE(fo.order_purchase_timestamp)) AS month,
            COUNT(DISTINCT fo.order_id)                              AS orders,
            ROUND(SUM(fo.price), 0)                                  AS revenue,
            ROUND(AVG(fr.review_score), 2)                           AS avg_review
        FROM `{MARTS}.fact_orders` fo
        LEFT JOIN `{MARTS}.fact_reviews` fr ON fo.order_id = fr.order_id
            AND DATE(fr.review_creation_date) >= DATE(fo.order_purchase_timestamp)
        WHERE fo.order_status = 'delivered'
          AND fo.order_id NOT IN ({EXCL})
        GROUP BY month ORDER BY month
    """)

    rfm = q(f"""
        SELECT rfm_segment,
            COUNT(*) AS customers,
            ROUND(AVG(monetary), 2) AS avg_spend,
            ROUND(AVG(recency_days), 0) AS avg_recency_days,
            COUNTIF(campaign_type IS NOT NULL) AS actionable
        FROM `{MARTS}.mart_rfm_scores`
        GROUP BY rfm_segment
        ORDER BY AVG(rfm_score) DESC
    """)

    campaigns = q(f"""
        SELECT campaign_type, COUNT(*) AS customers,
               ROUND(AVG(monetary), 2) AS avg_spend
        FROM `{MARTS}.mart_rfm_scores`
        WHERE campaign_type IS NOT NULL
        GROUP BY campaign_type ORDER BY customers DESC
    """)

    cohort_raw = q(f"""
        SELECT FORMAT_DATE('%Y-%m', cohort_month) AS cohort_month,
               months_since_first, retention_rate_pct
        FROM `{MARTS}.mart_cohort_retention`
        ORDER BY cohort_month, months_since_first
    """)
    pivot = cohort_raw.pivot(
        index='cohort_month', columns='months_since_first', values='retention_rate_pct'
    )
    cohort = {
        'z': [[None if pd.isna(v) else round(float(v), 1) for v in row]
              for row in pivot.values.tolist()],
        'x': [int(c) for c in pivot.columns.tolist()],
        'y': list(pivot.index),
    }

    cats = q(f"""
        WITH first_cat AS (
            SELECT dc.customer_unique_id,
                   dp.product_category_name_english AS category
            FROM `{MARTS}.fact_orders` fo
            JOIN `{MARTS}.dim_customers` dc ON fo.customer_id = dc.customer_id
            JOIN `{MARTS}.dim_products`  dp ON fo.product_id  = dp.product_id
            WHERE fo.order_status = 'delivered'
              AND fo.order_id NOT IN ({EXCL})
              AND dp.product_category_name_english IS NOT NULL
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY dc.customer_unique_id
                ORDER BY fo.order_purchase_timestamp
            ) = 1
        )
        SELECT fc.category,
               COUNT(*) AS cohort_size,
               ROUND(COUNTIF(mcs.total_orders > 1)/COUNT(*)*100, 1) AS return_rate_pct
        FROM first_cat fc
        JOIN `{MARTS}.mart_customer_summary` mcs USING (customer_unique_id)
        GROUP BY fc.category
        HAVING COUNT(*) >= 50
        ORDER BY return_rate_pct DESC
        LIMIT 20
    """)

    health_scores = q(f"SELECT health_score FROM `{MARTS}.mart_seller_health`")

    health_summary = q(f"""
        SELECT health_tier, trend_status, COUNT(*) AS sellers
        FROM `{MARTS}.mart_seller_health`
        GROUP BY health_tier, trend_status
    """)

    intervention = q(f"""
        SELECT seller_id, state, city, health_score, health_tier,
               recent_health_score, score_delta, trend_status, intervention_reason
        FROM `{MARTS}.mart_seller_health`
        WHERE intervention_reason IS NOT NULL
        ORDER BY
            CASE trend_status WHEN 'declining' THEN 1 WHEN 'inactive' THEN 2 ELSE 3 END,
            health_score ASC
        LIMIT 100
    """)

    print('  Done.')

    def _f(v):
        return None if pd.isna(v) else float(v)

    return {
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'kpi': {
            'total_orders':     int(kpi.total_orders),
            'unique_customers': int(kpi.unique_customers),
            'total_revenue':    float(kpi.total_revenue),
            'avg_order_value':  float(kpi.avg_order_value),
            'late_pct':         float(kpi.late_pct),
            'avg_review_score': float(kpi.avg_review_score),
            'repeat_pct':       float(repeat_pct),
        },
        'geo': [
            {
                'state': r.state, 'name': r.name,
                'lat': float(r.lat), 'lng': float(r.lng),
                'customers': int(r.customers), 'sellers': int(r.sellers),
                'customer_per_seller': _f(r.customer_per_seller),
                'avg_delivery_days':   _f(r.avg_delivery_days),
                'avg_freight':         _f(r.avg_freight),
                'late_pct':            _f(r.late_pct),
                'avg_health_score':    _f(r.avg_health_score),
                'churn_rate_pct':      _f(r.churn_rate_pct),
            }
            for _, r in geo.iterrows()
        ],
        'monthly': [
            {'month': r.month, 'orders': int(r.orders),
             'revenue': float(r.revenue),
             'avg_review': _f(r.avg_review)}
            for _, r in monthly.iterrows()
        ],
        'rfm': [
            {'segment': r.rfm_segment, 'customers': int(r.customers),
             'avg_spend': float(r.avg_spend), 'avg_recency': float(r.avg_recency_days),
             'actionable': int(r.actionable)}
            for _, r in rfm.iterrows()
        ],
        'campaigns': [
            {'type': r.campaign_type, 'customers': int(r.customers),
             'avg_spend': float(r.avg_spend)}
            for _, r in campaigns.iterrows()
        ],
        'cohort': cohort,
        'cats': [
            {'category': r.category.replace('_', ' ').title(),
             'cohort_size': int(r.cohort_size),
             'return_rate_pct': float(r.return_rate_pct)}
            for _, r in cats.iterrows()
        ],
        'health_scores': [float(v) for v in health_scores['health_score'].dropna().tolist()],
        'health_summary': [
            {'tier': r.health_tier, 'trend': r.trend_status, 'sellers': int(r.sellers)}
            for _, r in health_summary.iterrows()
        ],
        'intervention': [
            {
                'seller_id':      r.seller_id[:12] + '…',
                'state':          r.state,
                'city':           r.city.title(),
                'health_score':   float(r.health_score),
                'health_tier':    r.health_tier,
                'recent_score':   _f(r.recent_health_score),
                'score_delta':    float(r.score_delta),
                'trend_status':   r.trend_status,
                'reason':         r.intervention_reason,
            }
            for _, r in intervention.iterrows()
        ],
    }


# ── HTML template ───────────────────────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Olist Intelligence Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
:root {
  --navy:#0F172A; --navy2:#1E293B; --teal:#0EA5E9; --teal-l:#BAE6FD;
  --bg:#F1F5F9; --card:#FFFFFF; --border:#E2E8F0;
  --text:#1E293B; --muted:#64748B;
  --excellent:#16A34A; --good:#D97706; --at-risk:#EA580C; --critical:#DC2626;
  --stable:#2563EB; --declining:#DC2626; --inactive:#9CA3AF;
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;overflow:hidden;font-family:'Segoe UI',system-ui,sans-serif;color:var(--text);background:var(--bg)}

/* ── HEADER ── */
header{height:56px;background:var(--navy);display:flex;align-items:center;justify-content:space-between;padding:0 24px;flex-shrink:0;z-index:1000;position:relative}
header h1{color:#fff;font-size:18px;font-weight:700;letter-spacing:-.3px}
header .sub{color:var(--teal-l);font-size:12px;margin-top:2px}
.meta{color:#94A3B8;font-size:11px;text-align:right}

/* ── LAYOUT ── */
#layout{display:flex;height:calc(100vh - 56px)}

/* ── MAP PANEL (left) ── */
#map-panel{width:38%;display:flex;flex-direction:column;border-right:1px solid var(--border)}
#map{flex:1}
#map-footer{background:var(--navy);padding:12px 14px;flex-shrink:0}
.mode-label{color:#94A3B8;font-size:10px;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}
.mode-btns{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px}
.mode-btn{padding:4px 10px;border-radius:20px;border:1px solid #334155;background:transparent;color:#CBD5E1;font-size:11px;cursor:pointer;transition:all .15s}
.mode-btn:hover{border-color:var(--teal);color:var(--teal)}
.mode-btn.active{background:var(--teal);border-color:var(--teal);color:#fff;font-weight:600}
#map-legend{display:flex;align-items:center;gap:8px}
.legend-bar{flex:1;height:8px;border-radius:4px;background:linear-gradient(to right,#FEF9C3,#DC2626)}
.legend-labels{display:flex;justify-content:space-between;color:#94A3B8;font-size:10px;margin-top:3px}
.legend-text{color:#94A3B8;font-size:10px}

/* ── DASHBOARD PANEL (right) ── */
#dashboard{width:62%;display:flex;flex-direction:column;overflow:hidden}
#tabs{display:flex;gap:0;background:#fff;border-bottom:2px solid var(--border);padding:0 20px;flex-shrink:0}
.tab{padding:14px 20px;border:none;background:none;font-size:13px;font-weight:600;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all .15s;text-transform:uppercase;letter-spacing:.05em}
.tab:hover{color:var(--teal)}
.tab.active{color:var(--teal);border-bottom-color:var(--teal)}
#panes{flex:1;overflow-y:auto;padding:18px 20px}
.pane{display:none}
.pane.active{display:block}

/* ── CARDS ── */
.card{background:#fff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.08);padding:18px 20px;margin-bottom:14px}
.card-title{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-bottom:12px}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}

/* ── KPI CARDS ── */
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
.kpi-card{background:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08);border-top:3px solid var(--teal)}
.kpi-v{font-size:22px;font-weight:800;color:var(--navy);line-height:1}
.kpi-l{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-top:5px}
.kpi-card.warn{border-top-color:#D97706}
.kpi-card.good{border-top-color:#16A34A}
.kpi-card.danger{border-top-color:#DC2626}

/* ── SELLER KPIs ── */
.seller-kpi-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px}

/* ── INTERVENTION TABLE ── */
.tbl-controls{display:flex;gap:8px;margin-bottom:10px;align-items:center}
.tbl-filter{padding:5px 12px;border-radius:20px;border:1px solid var(--border);background:#fff;font-size:11px;color:var(--muted);cursor:pointer;transition:all .15s}
.tbl-filter:hover,.tbl-filter.active{background:var(--navy);color:#fff;border-color:var(--navy)}
.tbl-search{flex:1;padding:6px 12px;border-radius:8px;border:1px solid var(--border);font-size:12px;outline:none}
.tbl-search:focus{border-color:var(--teal)}
.tbl-count{font-size:11px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:8px 10px;background:var(--bg);font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);border-bottom:2px solid var(--border)}
td{padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:middle}
tr:hover td{background:#F8FAFC}
.tr-declining td:first-child{border-left:3px solid var(--critical)}
.tr-inactive td:first-child{border-left:3px solid var(--inactive)}
.tr-stable td:first-child{border-left:3px solid var(--stable)}
.badge{display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:600}
.badge-excellent{background:#DCFCE7;color:#15803D}
.badge-good{background:#FEF3C7;color:#B45309}
.badge-at_risk{background:#FFEDD5;color:#C2410C}
.badge-critical{background:#FEE2E2;color:#B91C1C}
.badge-declining{background:#FEE2E2;color:#B91C1C}
.badge-inactive{background:#F3F4F6;color:#6B7280}
.badge-stable{background:#DBEAFE;color:#1D4ED8}
.delta-neg{color:var(--critical);font-weight:600}
.delta-pos{color:var(--excellent);font-weight:600}
.reason-text{color:var(--muted);font-size:11px}

/* ── MAP: popups and labels ── */
.leaflet-popup-content{font-size:12px;line-height:1.7}
.popup-title{font-weight:700;font-size:13px;color:var(--navy);margin-bottom:6px}
.popup-row{display:flex;justify-content:space-between;gap:16px}
.popup-label{color:var(--muted)}
.popup-val{font-weight:600;color:var(--navy)}
</style>
</head>
<body>
<header>
  <div>
    <h1>Olist E-Commerce Intelligence</h1>
    <div class="sub">Seller Health &middot; Customer Retention &middot; Regional Analysis</div>
  </div>
  <div class="meta">
    <div>Olist Brazilian Dataset</div>
    <div id="gen-ts"></div>
  </div>
</header>

<div id="layout">

  <!-- ── LEFT: MAP ── -->
  <div id="map-panel">
    <div id="map"></div>
    <div id="map-footer">
      <div class="mode-label">Map view</div>
      <div class="mode-btns">
        <button class="mode-btn active" data-mode="customer_per_seller">Seller Gap</button>
        <button class="mode-btn" data-mode="avg_freight">Freight Cost</button>
        <button class="mode-btn" data-mode="avg_delivery_days">Delivery Days</button>
        <button class="mode-btn" data-mode="avg_health_score">Seller Health</button>
        <button class="mode-btn" data-mode="churn_rate_pct">Churn Rate</button>
      </div>
      <div id="map-legend">
        <span class="legend-text" id="legend-lo"></span>
        <div style="flex:1">
          <div class="legend-bar" id="legend-bar"></div>
          <div class="legend-labels"><span id="leg-min"></span><span id="leg-max"></span></div>
        </div>
        <span class="legend-text" id="legend-hi"></span>
      </div>
    </div>
  </div>

  <!-- ── RIGHT: DASHBOARD ── -->
  <div id="dashboard">
    <div id="tabs">
      <button class="tab active" data-tab="overview">Overview</button>
      <button class="tab" data-tab="customers">Customers</button>
      <button class="tab" data-tab="sellers">Seller Health</button>
    </div>

    <div id="panes">

      <!-- OVERVIEW -->
      <div class="pane active" id="pane-overview">
        <div class="kpi-grid" id="overview-kpis"></div>
        <div class="card">
          <div class="card-title">Monthly Revenue &amp; Review Score Trend</div>
          <div id="chart-monthly" style="height:290px"></div>
        </div>
      </div>

      <!-- CUSTOMERS -->
      <div class="pane" id="pane-customers">
        <div class="card">
          <div class="card-title">RFM Segmentation — Customer Base</div>
          <div id="chart-rfm" style="height:260px"></div>
        </div>
        <div class="card">
          <div class="card-title">Campaign Targets by Action Type</div>
          <div id="chart-campaign" style="height:200px"></div>
        </div>
        <div class="card">
          <div class="card-title">Cohort Retention Heatmap — % still active at month N</div>
          <div id="chart-cohort" style="height:380px"></div>
        </div>
        <div class="card">
          <div class="card-title">Repeat Purchase Rate by First-Order Category</div>
          <div id="chart-cats" style="height:380px"></div>
        </div>
      </div>

      <!-- SELLERS -->
      <div class="pane" id="pane-sellers">
        <div class="seller-kpi-grid" id="seller-kpis"></div>
        <div class="card">
          <div class="card-title">Health Score Distribution</div>
          <div id="chart-health-dist" style="height:260px"></div>
        </div>
        <div class="two-col">
          <div class="card">
            <div class="card-title">Sellers by Health Tier</div>
            <div id="chart-tier" style="height:230px"></div>
          </div>
          <div class="card">
            <div class="card-title">Seller Trend Status</div>
            <div id="chart-trend" style="height:230px"></div>
          </div>
        </div>
        <div class="card">
          <div class="card-title">Intervention List</div>
          <div class="tbl-controls">
            <button class="tbl-filter active" data-tf="all">All</button>
            <button class="tbl-filter" data-tf="declining">Declining</button>
            <button class="tbl-filter" data-tf="inactive">Inactive</button>
            <input class="tbl-search" id="tbl-search" type="text" placeholder="Filter by state or city…">
            <span class="tbl-count" id="row-count"></span>
          </div>
          <div style="overflow-x:auto">
            <table>
              <thead><tr>
                <th>Seller</th><th>Location</th><th>Health</th>
                <th>Recent</th><th>Delta</th><th>Trend</th><th>Reason</th>
              </tr></thead>
              <tbody id="intervention-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>

    </div><!-- /panes -->
  </div><!-- /dashboard -->

</div><!-- /layout -->

<script>
/*INLINE_DATA*/

// ── Shared Plotly layout factory ─────────────────────────────────────────────
const PL = (extra={}) => Object.assign({
  margin:{l:56,r:16,t:32,b:48},
  paper_bgcolor:'white', plot_bgcolor:'#F8FAFC',
  font:{family:'Segoe UI,system-ui,sans-serif',color:'#1E293B',size:12},
  showlegend:true, legend:{font:{size:11}},
}, extra);
const PC = {displayModeBar:false, responsive:true};

// ── Segment / campaign colors ────────────────────────────────────────────────
const SEG_COLORS = {
  champions:'#14532D', loyal_customers:'#166534', promising:'#4ADE80',
  potential_loyalists:'#D97706', at_risk:'#EA580C', lost:'#991B1B',
};
const CAMP_COLORS = {
  loyalty_reward:'#14532D', nurture:'#0EA5E9', second_purchase:'#8B5CF6',
  winback:'#EA580C', reactivation:'#991B1B',
};
const TIER_COLORS = {excellent:'#16A34A', good:'#D97706', at_risk:'#EA580C', critical:'#DC2626'};
const TREND_COLORS = {stable:'#2563EB', declining:'#DC2626', inactive:'#9CA3AF'};

// ── Map setup ────────────────────────────────────────────────────────────────
document.getElementById('gen-ts').textContent = 'Updated ' + D.generated;

const map = L.map('map', {zoomControl:true, attributionControl:false})
             .setView([-15, -52], 4);

L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
  maxZoom:18, attribution:''
}).addTo(map);

// 1. Grey overlay on neighbouring countries — ocean (no polygon) stays blue
fetch('https://raw.githubusercontent.com/holtzy/D3-graph-gallery/master/DATA/world.geojson')
  .then(r => r.json())
  .then(gj => {
    const nonBrazil = {
      type:'FeatureCollection',
      features: gj.features.filter(f => {
        const p = f.properties || {};
        const name = (p.name || p.NAME || p.admin || '').toLowerCase();
        const iso  = (p.iso_a3 || p.ISO_A3 || p.ADM0_A3 || '').toUpperCase();
        return name !== 'brazil' && iso !== 'BRA';
      })
    };
    L.geoJSON(nonBrazil, {
      style:{fillColor:'#94A3B8', fillOpacity:0.28, color:'#94A3B8', weight:0.4, opacity:0.4},
      interactive:false
    }).addTo(map);
  }).catch(()=>{});

// 2. Brazil state borders on top for visual boundary reference
fetch('https://raw.githubusercontent.com/codeforgermany/click_that_hood/master/public/data/brazil-states.geojson')
  .then(r => r.json())
  .then(gj => {
    L.geoJSON(gj, {
      style:{color:'#475569', weight:0.8, fillOpacity:0, opacity:0.6},
      interactive:false
    }).addTo(map);
  }).catch(()=>{});

// ── Map mode config ──────────────────────────────────────────────────────────
const MODES = {
  customer_per_seller: {label:'Seller Gap',      unit:'×',   dir:'bad',  grad:['#FEF9C3','#DC2626']},
  avg_freight:         {label:'Avg Freight',      unit:'R$',  dir:'bad',  grad:['#FEF9C3','#DC2626']},
  avg_delivery_days:   {label:'Avg Delivery',     unit:'d',   dir:'bad',  grad:['#FEF9C3','#DC2626']},
  avg_health_score:    {label:'Seller Health',    unit:'/100',dir:'good', grad:['#FEE2E2','#16A34A']},
  churn_rate_pct:      {label:'Churn Rate',       unit:'%',   dir:'bad',  grad:['#FEF9C3','#DC2626']},
};

let currentMode = 'customer_per_seller';
let markers = [];

function colorFromGradient(t, grad) {
  const h = c => [parseInt(c.slice(1,3),16), parseInt(c.slice(3,5),16), parseInt(c.slice(5,7),16)];
  const a = h(grad[0]), b = h(grad[1]);
  const r = Math.round(a[0]+(b[0]-a[0])*t);
  const g = Math.round(a[1]+(b[1]-a[1])*t);
  const bl = Math.round(a[2]+(b[2]-a[2])*t);
  return `rgb(${r},${g},${bl})`;
}

function drawMarkers(mode) {
  markers.forEach(m => m.remove());
  markers = [];
  const cfg = MODES[mode];
  const vals = D.geo.map(s => s[mode]).filter(v => v !== null);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const maxC = Math.max(...D.geo.map(s => s.customers));

  document.getElementById('leg-min').textContent = lo.toFixed(1) + cfg.unit;
  document.getElementById('leg-max').textContent = hi.toFixed(1) + cfg.unit;
  document.getElementById('legend-bar').style.background =
    `linear-gradient(to right,${cfg.grad[0]},${cfg.grad[1]})`;

  D.geo.forEach(s => {
    const raw = s[mode];
    if (raw === null || s.lat === 0) return;
    const t = hi === lo ? 0.5 : (raw - lo) / (hi - lo);
    const col = colorFromGradient(t, cfg.grad);
    const r = 6 + (s.customers / maxC) * 22;

    const pop = `
      <div class="popup-title">${s.name} (${s.state})</div>
      <div class="popup-row"><span class="popup-label">Customers</span><span class="popup-val">${s.customers.toLocaleString()}</span></div>
      <div class="popup-row"><span class="popup-label">Sellers</span><span class="popup-val">${s.sellers}</span></div>
      <div class="popup-row"><span class="popup-label">Customer/Seller</span><span class="popup-val">${s.customer_per_seller !== null ? s.customer_per_seller+'×' : 'N/A'}</span></div>
      <div class="popup-row"><span class="popup-label">Avg Delivery</span><span class="popup-val">${s.avg_delivery_days !== null ? s.avg_delivery_days+'d' : 'N/A'}</span></div>
      <div class="popup-row"><span class="popup-label">Avg Freight</span><span class="popup-val">${s.avg_freight !== null ? 'R$'+s.avg_freight : 'N/A'}</span></div>
      <div class="popup-row"><span class="popup-label">Late Orders</span><span class="popup-val">${s.late_pct !== null ? s.late_pct+'%' : 'N/A'}</span></div>
      <div class="popup-row"><span class="popup-label">Seller Health</span><span class="popup-val">${s.avg_health_score !== null ? s.avg_health_score+'/100' : 'N/A'}</span></div>
      <div class="popup-row"><span class="popup-label">Churn Rate</span><span class="popup-val">${s.churn_rate_pct !== null ? s.churn_rate_pct+'%' : 'N/A'}</span></div>
    `;
    const m = L.circleMarker([s.lat, s.lng], {
      radius:r, color:'white', weight:1.5,
      fillColor:col, fillOpacity:0.88
    }).bindPopup(pop).addTo(map);

    // State label
    L.marker([s.lat, s.lng], {
      icon: L.divIcon({
        className:'', iconSize:[0,0],
        html:`<span style="font-size:9px;font-weight:700;color:#1E293B;text-shadow:0 0 3px #fff,0 0 3px #fff">${s.state}</span>`
      })
    }).addTo(map);

    markers.push(m);
  });
}

document.querySelectorAll('.mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentMode = btn.dataset.mode;
    drawMarkers(currentMode);
  });
});

drawMarkers(currentMode);

// ── Tab switching ─────────────────────────────────────────────────────────────
const rendered = {};
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.pane').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const id = 'pane-' + tab.dataset.tab;
    document.getElementById(id).classList.add('active');
    if (!rendered[id]) { renderTab(tab.dataset.tab); rendered[id] = true; }
    map.invalidateSize();
  });
});

// ── Render charts ─────────────────────────────────────────────────────────────
function renderTab(tab) {
  if (tab === 'overview') renderOverview();
  if (tab === 'customers') renderCustomers();
  if (tab === 'sellers') renderSellers();
}

// ── OVERVIEW ─────────────────────────────────────────────────────────────────
function fmt(n, prefix='', suffix='') {
  if (n >= 1e6) return prefix + (n/1e6).toFixed(1) + 'M' + suffix;
  if (n >= 1e3) return prefix + (n/1e3).toFixed(1) + 'K' + suffix;
  return prefix + n.toLocaleString() + suffix;
}

function renderOverview() {
  const K = D.kpi;
  const cards = [
    {v: fmt(K.total_orders),     l:'Total Orders',       cls:''},
    {v: fmt(K.unique_customers), l:'Unique Customers',   cls:''},
    {v: fmt(K.total_revenue,'R$'), l:'Total Revenue',    cls:''},
    {v: 'R$'+K.avg_order_value,  l:'Avg Order Value',   cls:''},
    {v: K.repeat_pct+'%',        l:'Repeat Purchase Rate', cls:'good'},
    {v: K.late_pct+'%',          l:'Late Delivery Rate', cls:'warn'},
    {v: K.avg_review_score+' ★', l:'Avg Review Score',  cls:'good'},
  ];
  // 4-col grid: first row 4 cards, second row 3
  document.getElementById('overview-kpis').innerHTML = cards.slice(0,4).map(c =>
    `<div class="kpi-card ${c.cls}"><div class="kpi-v">${c.v}</div><div class="kpi-l">${c.l}</div></div>`
  ).join('');
  // Append row 2 as a wider card
  const row2 = document.createElement('div');
  row2.style.cssText = 'grid-column:1/-1;display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:0';
  row2.innerHTML = cards.slice(4).map(c =>
    `<div class="kpi-card ${c.cls}"><div class="kpi-v">${c.v}</div><div class="kpi-l">${c.l}</div></div>`
  ).join('');
  document.getElementById('overview-kpis').appendChild(row2);

  // Monthly trend
  const months = D.monthly.map(m => m.month);
  Plotly.newPlot('chart-monthly', [
    {
      type:'bar', x:months, y:D.monthly.map(m => m.revenue),
      name:'Revenue (R$)', marker:{color:'#0EA5E9', opacity:0.85},
      yaxis:'y', hovertemplate:'%{x}<br>R$%{y:,.0f}<extra></extra>'
    },
    {
      type:'scatter', mode:'lines+markers', x:months,
      y:D.monthly.map(m => m.avg_review), name:'Avg Review ★',
      line:{color:'#16A34A', width:2}, marker:{size:5},
      yaxis:'y2', hovertemplate:'%{x}<br>★ %{y:.2f}<extra></extra>'
    }
  ], PL({
    xaxis:{tickangle:-45, tickfont:{size:10}},
    yaxis:{title:'Revenue (R$)', tickformat:',.0f', titlefont:{size:11}},
    yaxis2:{title:'Review Score', overlaying:'y', side:'right',
            range:[1,5], tickfont:{size:10}, titlefont:{size:11}},
    legend:{orientation:'h', y:1.08},
    margin:{l:64,r:52,t:32,b:72}
  }), PC);
}

// ── CUSTOMERS ─────────────────────────────────────────────────────────────────
function renderCustomers() {
  // RFM segments
  const segs = D.rfm.map(r => r.segment.replace(/_/g,' '));
  Plotly.newPlot('chart-rfm', [{
    type:'bar', orientation:'h',
    y:segs, x:D.rfm.map(r => r.customers),
    marker:{color:D.rfm.map(r => SEG_COLORS[r.segment]||'#94A3B8')},
    name:'Customers',
    hovertemplate:'<b>%{y}</b><br>%{x:,} customers<br>Avg spend: R$%{customdata[0]:,.0f}<br>Avg recency: %{customdata[1]} days<extra></extra>',
    customdata:D.rfm.map(r => [r.avg_spend, r.avg_recency])
  }], PL({
    xaxis:{title:'Number of Customers'},
    yaxis:{autorange:'reversed'},
    showlegend:false,
    margin:{l:130,r:16,t:24,b:48}
  }), PC);

  // Campaign targets
  const camps = D.campaigns.map(c => c.type.replace(/_/g,' '));
  Plotly.newPlot('chart-campaign', [{
    type:'bar', orientation:'h',
    y:camps, x:D.campaigns.map(c => c.customers),
    marker:{color:D.campaigns.map(c => CAMP_COLORS[c.type]||'#94A3B8')},
    hovertemplate:'<b>%{y}</b><br>%{x:,} customers<br>Avg spend: R$%{customdata:,.0f}<extra></extra>',
    customdata:D.campaigns.map(c => c.avg_spend)
  }], PL({
    xaxis:{title:'Customers Assigned'},
    yaxis:{autorange:'reversed'},
    showlegend:false,
    margin:{l:120,r:16,t:16,b:48}
  }), PC);

  // Cohort heatmap
  Plotly.newPlot('chart-cohort', [{
    type:'heatmap',
    z:D.cohort.z, x:D.cohort.x, y:D.cohort.y,
    colorscale:[[0,'#EFF6FF'],[0.33,'#93C5FD'],[0.66,'#3B82F6'],[1,'#1E3A8A']],
    zmin:0, zmax:100,
    colorbar:{title:'Retention %', len:0.8, thickness:14, tickfont:{size:10}},
    hovertemplate:'Cohort: %{y}<br>Month +%{x}: <b>%{z:.1f}%</b><extra></extra>',
    xgap:1, ygap:1
  }], PL({
    xaxis:{title:'Months Since First Order', tickmode:'linear'},
    yaxis:{title:'Acquisition Cohort', autorange:'reversed', tickfont:{size:10}},
    showlegend:false,
    margin:{l:72,r:60,t:16,b:52}
  }), PC);

  // Category repeat rate
  const avg = D.cats.reduce((s,c)=>s+c.return_rate_pct,0)/D.cats.length;
  Plotly.newPlot('chart-cats', [{
    type:'bar', orientation:'h',
    y:D.cats.map(c => c.category),
    x:D.cats.map(c => c.return_rate_pct),
    marker:{color:D.cats.map(c => c.return_rate_pct >= avg ? '#0EA5E9' : '#BAE6FD')},
    hovertemplate:'<b>%{y}</b><br>Repeat rate: %{x:.1f}%<br>Cohort: %{customdata:,}<extra></extra>',
    customdata:D.cats.map(c => c.cohort_size)
  },{
    type:'scatter', mode:'lines', x:[avg,avg], y:[D.cats[D.cats.length-1].category, D.cats[0].category],
    name:'Platform avg', line:{color:'#DC2626', dash:'dot', width:1.5}
  }], PL({
    xaxis:{title:'Repeat Purchase Rate (%)'},
    yaxis:{autorange:'reversed', tickfont:{size:10}},
    showlegend:true,
    legend:{x:0.7, y:0.05},
    margin:{l:170,r:16,t:16,b:48}
  }), PC);
}

// ── SELLERS ──────────────────────────────────────────────────────────────────
function renderSellers() {
  const scores = D.health_scores;
  const total = scores.length;
  const needsAction = D.intervention.length;
  const avgScore = (scores.reduce((a,b)=>a+b,0)/total).toFixed(1);

  document.getElementById('seller-kpis').innerHTML = [
    {v: total.toLocaleString(), l:'Total Sellers',          cls:''},
    {v: needsAction.toLocaleString(), l:'Needing Intervention', cls:'warn'},
    {v: avgScore+' / 100',     l:'Avg Health Score',        cls:'good'},
  ].map(c => `<div class="kpi-card ${c.cls}"><div class="kpi-v">${c.v}</div><div class="kpi-l">${c.l}</div></div>`).join('');

  // Health score histogram
  Plotly.newPlot('chart-health-dist', [{
    type:'histogram', x:scores, nbinsx:20,
    marker:{color:'#0EA5E9', opacity:0.85, line:{color:'white', width:0.5}},
    hovertemplate:'Score %{x:.0f}–%{x:.0f}<br>%{y} sellers<extra></extra>'
  }], PL({
    shapes:[40,60,80].map((t,i) => ({
      type:'line', x0:t, x1:t, y0:0, y1:1, yref:'paper',
      line:{color:['#DC2626','#EA580C','#16A34A'][i], dash:'dash', width:1.5}
    })),
    annotations:[
      {x:20, y:1, yref:'paper', text:'critical', showarrow:false, font:{size:10, color:'#DC2626'}},
      {x:50, y:1, yref:'paper', text:'at_risk',  showarrow:false, font:{size:10, color:'#EA580C'}},
      {x:70, y:1, yref:'paper', text:'good',     showarrow:false, font:{size:10, color:'#D97706'}},
      {x:90, y:1, yref:'paper', text:'excellent',showarrow:false, font:{size:10, color:'#16A34A'}},
    ],
    xaxis:{title:'Health Score (0–100)', range:[0,100]},
    yaxis:{title:'Number of Sellers'},
    showlegend:false, margin:{l:56,r:16,t:32,b:52}
  }), PC);

  // Tier breakdown
  const tierOrder = ['excellent','good','at_risk','critical'];
  const tierCounts = {};
  D.health_summary.forEach(r => { tierCounts[r.tier] = (tierCounts[r.tier]||0) + r.sellers; });
  Plotly.newPlot('chart-tier', [{
    type:'bar',
    x:tierOrder.map(t => t.replace('_',' ')),
    y:tierOrder.map(t => tierCounts[t]||0),
    marker:{color:tierOrder.map(t => TIER_COLORS[t])},
    text:tierOrder.map(t => tierCounts[t]||0),
    textposition:'outside', textfont:{size:11},
    hovertemplate:'%{x}<br>%{y:,} sellers<extra></extra>'
  }], PL({
    xaxis:{title:''}, yaxis:{title:'Sellers'},
    showlegend:false, margin:{l:48,r:16,t:32,b:40}
  }), PC);

  // Trend status
  const trendOrder = ['stable','declining','inactive'];
  const trendCounts = {};
  D.health_summary.forEach(r => { trendCounts[r.trend] = (trendCounts[r.trend]||0) + r.sellers; });
  Plotly.newPlot('chart-trend', [{
    type:'bar',
    x:trendOrder,
    y:trendOrder.map(t => trendCounts[t]||0),
    marker:{color:trendOrder.map(t => TREND_COLORS[t])},
    text:trendOrder.map(t => trendCounts[t]||0),
    textposition:'outside', textfont:{size:11},
    hovertemplate:'%{x}<br>%{y:,} sellers<extra></extra>'
  }], PL({
    xaxis:{title:''}, yaxis:{title:'Sellers'},
    showlegend:false, margin:{l:48,r:16,t:32,b:40}
  }), PC);

  // Intervention table
  let tableFilter = 'all';
  let tableSearch = '';

  function renderTable() {
    const rows = D.intervention
      .filter(r => tableFilter === 'all' || r.trend_status === tableFilter)
      .filter(r => !tableSearch
        || r.state.includes(tableSearch.toUpperCase())
        || r.city.toLowerCase().includes(tableSearch.toLowerCase()));
    document.getElementById('row-count').textContent = rows.length + ' sellers';
    document.getElementById('intervention-tbody').innerHTML = rows.map(r => {
      const delta = r.score_delta !== null ? (r.score_delta > 0 ? '+'+r.score_delta : r.score_delta) : '—';
      const dCls = r.score_delta < 0 ? 'delta-neg' : 'delta-pos';
      return `<tr class="tr-${r.trend_status}">
        <td style="font-size:10px;font-family:monospace;color:#64748B">${r.seller_id}</td>
        <td><strong>${r.state}</strong> · ${r.city}</td>
        <td>
          <span style="font-weight:700">${r.health_score}</span>
          <span class="badge badge-${r.health_tier}" style="margin-left:4px">${r.health_tier.replace('_',' ')}</span>
        </td>
        <td>${r.recent_score !== null ? r.recent_score : '—'}</td>
        <td class="${dCls}">${delta}</td>
        <td><span class="badge badge-${r.trend_status}">${r.trend_status}</span></td>
        <td class="reason-text">${r.reason}</td>
      </tr>`;
    }).join('');
  }

  document.querySelectorAll('.tbl-filter').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tbl-filter').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      tableFilter = btn.dataset.tf;
      renderTable();
    });
  });
  document.getElementById('tbl-search').addEventListener('input', e => {
    tableSearch = e.target.value;
    renderTable();
  });

  renderTable();
}

// ── Init overview on load ─────────────────────────────────────────────────────
renderTab('overview');
rendered['pane-overview'] = true;
</script>
</body>
</html>"""


def build_html(data):
    data_json = json.dumps(data, cls=BQEncoder, ensure_ascii=False)
    return HTML_TEMPLATE.replace('/*INLINE_DATA*/', f'const D = {data_json};')


def main():
    data = fetch()
    html = build_html(data)
    OUT.write_text(html, encoding='utf-8')
    kb = OUT.stat().st_size // 1024
    print(f'Dashboard written → {OUT}  ({kb} KB)')
    print('Next steps:')
    print('  git add docs/index.html')
    print('  git commit -m "dashboard: update data snapshot"')
    print('  git push')
    print('  Live at: https://maycoooz.github.io/ELT_olist/')


if __name__ == '__main__':
    main()
