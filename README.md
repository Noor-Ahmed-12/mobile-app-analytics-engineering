## Project architecture

The project follows a simple analytics-engineering workflow that separates ingestion, data validation, transformation, modelling, analysis, and presentation.

```mermaid
flowchart TD
    A[Install CSV] --> C[build_database.py]
    B[Revenue CSV] --> C

    C --> D[(SQLite Database)]

    D --> E[installs_raw]
    D --> F[revenue_raw]

    E --> G[Data Quality Checks]
    F --> G

    G --> H[installs_clean]
    G --> I[revenue_clean]

    H --> J[app_installs CTE]
    I --> K[month_revenue CTE]

    K --> L[Aggregate Revenue to Install Grain]
    J --> M[LEFT JOIN]
    L --> M

    M --> N[app_analysis_base]

    N --> O[Headline Metrics]
    N --> P[Network Analysis]
    N --> Q[Country Analysis]
    N --> R[App Version Analysis]
    N --> S[Daily Cohort Analysis]

    O --> T[Python Summary]
    P --> U[Matplotlib Charts]
    Q --> U
    R --> U
    S --> U

    N --> V[Tableau Dashboard]
    U --> W[Business Report]
    V --> W
```

### Architecture layers

| Layer              | Purpose                                                                             |
| ------------------ | ----------------------------------------------------------------------------------- |
| Source layer       | Contains install-level and event-level CSV files                                    |
| Ingestion layer    | Loads and standardizes the source files with `build_database.py`                    |
| Raw layer          | Stores source-aligned tables in SQLite                                              |
| Validation layer   | Checks duplicates, missing keys, orphan records, date coverage, and event anomalies |
| Cleaning layer     | Produces one row per install and one row per revenue event                          |
| Modelling layer    | Aggregates revenue to install grain and creates the central analysis table          |
| Metrics layer      | Calculates profitability, ARPI, ARPPU, ROAS, ROI, and payer rate                    |
| Presentation layer | Produces charts, Tableau views, and business recommendations                        |

---

## Data flow

```text
Install CSV                     Revenue CSV
     |                               |
     +--------------+----------------+
                    |
                    v
             build_database.py
                    |
                    v
               SQLite database
                    |
          +---------+---------+
          |                   |
          v                   v
    installs_raw         revenue_raw
          |                   |
          v                   v
   installs_clean       revenue_clean
          |                   |
          |          aggregate by install ID
          |                   |
          +---------+---------+
                    |
                 LEFT JOIN
                    |
                    v
          app_analysis_base
          one row per install
                    |
        +-----------+------------+
        |           |            |
        v           v            v
     Metrics      Charts      Tableau
```

---

## Table relationships

```mermaid
erDiagram
    INSTALLS_RAW {
        string user_install_id
        integer client
        string geo_country_code
        string client_version
        integer network_id
        date install_event_date
    }

    REVENUE_RAW {
        string id
        string user_install_id
        float money_value_usd
        integer event_count
        date event_date
    }

    INSTALLS_CLEAN {
        string user_install_id
        integer client
        string geo_country_code
        string client_version
        integer network_id
        date install_event_date
    }

    REVENUE_CLEAN {
        string id
        string user_install_id
        float money_value_usd
        integer event_count
        date event_date
    }

    APP_ANALYSIS_BASE {
        string user_install_id
        string geo_country_code
        string client_version
        integer network_id
        date install_event_date
        float revenue
    }

    INSTALLS_RAW ||--|| INSTALLS_CLEAN : deduplicated_to
    REVENUE_RAW ||--|| REVENUE_CLEAN : deduplicated_to
    INSTALLS_CLEAN ||--o{ REVENUE_CLEAN : user_install_id
    INSTALLS_CLEAN ||--|| APP_ANALYSIS_BASE : modelled_to
```

---

## Data grain

The most important modelling decision was defining what one row represents in each table.

| Table               | Grain                                                                |
| ------------------- | -------------------------------------------------------------------- |
| `installs_raw`      | Intended one row per app install, with duplicate IDs present         |
| `revenue_raw`       | Intended one row per revenue event, with duplicate event IDs present |
| `installs_clean`    | One row per unique `user_install_id`                                 |
| `revenue_clean`     | One row per unique revenue-event `id`                                |
| `month_revenue`     | One row per install ID with aggregated monthly revenue               |
| `app_analysis_base` | One row per analysed install with total attributed revenue           |

Revenue is aggregated before the join because one installation can generate multiple revenue events.

---

## Data preview

### Install-level source data

Example structure:

| user_install_id | client | country | version | network_id | install_date |
| --------------- | -----: | ------- | ------: | ---------: | ------------ |
| install_001     |    174 | US      |     502 |         58 | 2024-04-03   |
| install_002     |    174 | FR      |     504 |         60 | 2024-04-24   |
| install_003     |    174 | US      |     502 |         58 | 2024-04-08   |

One row represents one app installation.

### Revenue-event source data

Example structure:

| event_id  | user_install_id | money_value_usd | event_count | event_date |
| --------- | --------------- | --------------: | ----------: | ---------- |
| event_001 | install_001     |            1.25 |           1 | 2024-04-04 |
| event_002 | install_001     |            2.10 |           1 | 2024-04-07 |
| event_003 | install_002     |            0.75 |           1 | 2024-04-25 |

One install may appear in multiple revenue-event rows.

### Final install-level analytical model

Example structure:

| user_install_id | country | version | network_id | install_date | revenue |
| --------------- | ------- | ------: | ---------: | ------------ | ------: |
| install_001     | US      |     502 |         58 | 2024-04-03   |    3.35 |
| install_002     | FR      |     504 |         60 | 2024-04-24   |    0.75 |
| install_003     | US      |     502 |         58 | 2024-04-08   |    0.00 |

The final model contains one row per install. Revenue events are summed before being joined to the installation record.

---

## Data transformation example

### Before aggregation

```text
Install ID: install_001

Revenue events:
$1.25
$2.10
$0.75
```

### After aggregation

```text
install_001 total revenue = $4.10
```

### Final model

```text
One install row
+
One aggregated revenue value
=
Safe profitability calculation
```

This prevents one installation from being counted multiple times.

---

## Dashboard preview

### Tableau overview

The dashboard presents:
* Headline profitability metrics
* Network-level profit contribution
* Revenue per install versus break-even
* Country comparison
* App-version performance
* Daily install cohort performance

![Tableau dashboard](https://github.com/Noor-Ahmed-12/mobile-app-analytics-engineering/blob/main/tableau/tablaueDsh.png)


### Network profitability

![Network profit chart](charts/net_profit_by_network.png)

### Network ARPI versus break-even

![Network ARPI chart](charts/arpi_by_network.png)

### Country profitability

![Country profit chart](charts/profit_by_country.png)

### App-version profitability

![App version chart](charts/net_profit_by_version.png)

### Daily cohort performance

![Daily cohort chart](https://github.com/Noor-Ahmed-12/mobile-app-analytics-engineering/blob/main/charts/daily_trend.png)
