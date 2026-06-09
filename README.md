# ELT Olist — Brazilian E-Commerce Pipeline

An end-to-end ELT pipeline using the [Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) from Kaggle.

## Tech Stack

| Tool | Purpose |
|---|---|
| Supabase (PostgreSQL) | Source system — holds raw CSV data |
| Meltano | Extract from Supabase, load into BigQuery |
| BigQuery | Data warehouse |
| dbt | Transformations, testing, star schema |
| Dagster | Orchestration (planned) |

## Project Structure

```
ELT_olist/
├── m2-environment.yml          # Conda environment
├── olist_meltano/              # Meltano EL pipeline (Supabase → BigQuery)
│   ├── meltano.yml
│   └── .env.example
└── olist_transform/            # dbt transformation layer
    ├── profiles.yml
    ├── dbt_project.yml
    ├── packages.yml
    └── models/
        ├── staging/            # 8 staging views (one per source table)
        └── marts/              # 5 mart tables (star schema)
```

## Data Model

The raw data consists of 9 tables (~1.1M records) loaded into BigQuery under the `olist_raw` dataset.

### Staging Layer (`olist_transformed_staging`)
8 views — one per source table. Light cleaning only: type casting, column renaming, zip code padding (Brazilian CEP codes are always 5 digits), and product category translation joined into `stg_products`.

### Marts Layer (`olist_transformed_marts`)

| Model | Description | Sample Questions |
|---|---|---|
| `dim_customers` | Customers enriched with lat/lng from geolocation | Customer distribution by state, repeat vs one-time buyers |
| `dim_products` | Products with English category name, photos, dimensions | Best performing categories, does photo count affect sales? |
| `dim_sellers` | Sellers enriched with lat/lng from geolocation | Seller distribution by state, top sellers by revenue |
| `fact_orders` | One row per order item — joins orders, items, payments. Includes `delivery_days`, `estimated_delivery_days`, `is_late` | Revenue by month/category/state, late delivery rate, freight analysis |
| `fact_reviews` | One row per review with `sentiment` derived from `review_score` | Average score by seller/product, sentiment distribution, delivery vs rating correlation |

---

## Setup Instructions (For Group Members)

### Prerequisites
- [Anaconda](https://www.anaconda.com/download) or Miniconda installed
- The service account JSON key file — ask the project owner (Marcus) to share it with you securely

### Step 1 — Clone the repo
```bash
git clone <repo-url>
cd ELT_olist
```

### Step 2 — Create and activate conda environment
```bash
conda env create -f m2-environment.yml
conda activate m2
```

### Step 3 — Save BigQuery credentials
Save the service account JSON key file somewhere safe on your machine **outside the repo** (e.g. `~/.gcp/olist-key.json`). Note the full path.

### Step 4 — Configure dbt
Open `olist_transform/profiles.yml` and update the `keyfile` path to where you saved your JSON key:
```yaml
keyfile: /YOUR/PATH/TO/your-key.json
```

### Step 5 — Install dbt packages
```bash
cd olist_transform
dbt deps
```

### Step 6 — Run dbt models
```bash
dbt run
```

### Step 7 — Run dbt tests
```bash
dbt test
```

> All dbt commands should be run from inside the `olist_transform/` directory.

---

## Note on Meltano (Optional)

The data is already loaded into BigQuery — you do not need to run Meltano unless you want to reload the raw data from scratch.

If you do need to re-run the pipeline:
1. Copy `olist_meltano/.env.example` to `olist_meltano/.env` and fill in your Supabase connection string
2. Update `credentials_path` in `olist_meltano/meltano.yml` to your local key file path
3. Run from inside `olist_meltano/`:
```bash
meltano run tap-postgres target-bigquery
```
