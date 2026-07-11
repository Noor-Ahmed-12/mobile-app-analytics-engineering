## Project architecture

The project follows a layered analytics-engineering workflow that separates ingestion, validation, cleaning, modelling, analysis, and presentation.

```mermaid
flowchart LR
    subgraph A[Source data]
        A1[installs.csv<br/>Install-level data]
        A2[revenue.csv<br/>Event-level data]
    end

    subgraph B[Ingestion]
        B1[build_database.py]
        B2[(SQLite Database)]
    end

    subgraph C[Raw models]
        C1[installs_raw]
        C2[revenue_raw]
    end

    subgraph D[Validation and cleaning]
        D1[Data-quality checks]
        D2[installs_clean<br/>One row per install]
        D3[revenue_clean<br/>One row per revenue event]
    end

    subgraph E[Analytical modelling]
        E1[app_installs<br/>Filtered install cohort]
        E2[month_revenue<br/>Revenue aggregated by install]
        E3[LEFT JOIN]
        E4[app_analysis_base<br/>One row per analysed install]
    end

    subgraph F[Analytics outputs]
        F1[Headline metrics]
        F2[Network analysis]
        F3[Country analysis]
        F4[Version analysis]
        F5[Daily cohort analysis]
        F6[Matplotlib charts]
        F7[Tableau dashboard]
        F8[Business report]
    end

    A1 --> B1
    A2 --> B1
    B1 --> B2

    B2 --> C1
    B2 --> C2

    C1 --> D1
    C2 --> D1
    D1 --> D2
    D1 --> D3

    D2 --> E1
    D3 --> E2
    E1 --> E3
    E2 --> E3
    E3 --> E4

    E4 --> F1
    E4 --> F2
    E4 --> F3
    E4 --> F4
    E4 --> F5

    F1 --> F8
    F2 --> F6
    F3 --> F6
    F4 --> F6
    F5 --> F6
    E4 --> F7
    F6 --> F8
    F7 --> F8
```

### Architecture layers

| Layer        | Purpose                                                                        |
| ------------ | ------------------------------------------------------------------------------ |
| Source       | Install-level and revenue-event CSV files                                      |
| Ingestion    | Loads and standardizes source files using `build_database.py`                  |
| Raw models   | Stores source-aligned data in SQLite                                           |
| Validation   | Checks duplicate keys, missing IDs, orphan records, dates, and event anomalies |
| Cleaning     | Creates one row per install and one row per unique revenue event               |
| Modelling    | Aggregates revenue to install grain and creates the central analytical table   |
| Metrics      | Calculates profitability, ARPI, ARPPU, ROAS, ROI, and payer rate               |
| Presentation | Produces Python charts, a Tableau dashboard, and business recommendations      |

---

## Core data model

The source tables have different grains:

```mermaid
flowchart LR
    A[installs_clean<br/>One row per install]

    B[revenue_clean<br/>One row per revenue event]
    B --> C[GROUP BY user_install_id]

    C --> D[month_revenue<br/>One row per install]

    A --> E[LEFT JOIN]
    D --> E

    E --> F[app_analysis_base<br/>One row per analysed install]
```

One installation may generate zero, one, or many revenue events:

```mermaid
erDiagram
    INSTALLS_CLEAN ||--o{ REVENUE_CLEAN : "generates"

    INSTALLS_CLEAN {
        string user_install_id PK
        integer client
        string geo_country_code
        string client_version
        integer network_id
        date install_event_date
    }

    REVENUE_CLEAN {
        string id PK
        string user_install_id FK
        float money_value_usd
        integer event_count
        date event_date
    }
```

Revenue is aggregated before the join to prevent:

* Duplicate install counts
* Repeated acquisition costs
* Inflated segment volume
* Incorrect ARPI and profitability calculations

---

## Data grain

| Model               | Grain                                                                |
| ------------------- | -------------------------------------------------------------------- |
| `installs_raw`      | Intended one row per app install; duplicate IDs were present         |
| `revenue_raw`       | Intended one row per revenue event; duplicate event IDs were present |
| `installs_clean`    | One row per unique `user_install_id`                                 |
| `revenue_clean`     | One row per unique revenue-event `id`                                |
| `month_revenue`     | One row per install ID with aggregated monthly revenue               |
| `app_analysis_base` | One row per analysed install with total attributed revenue           |


---

## Synthetic data preview

The original source data is not included. The examples below are synthetic records that reproduce the project’s data structure.

### Install-level source data

| user_install_id | client | country | version | network_id | install_date |
| --------------- | -----: | ------- | ------: | ---------: | ------------ |
| install_001     |    174 | US      |     502 |         58 | 2024-04-03   |
| install_002     |    174 | FR      |     504 |         60 | 2024-04-24   |
| install_003     |    174 | US      |     502 |         58 | 2024-04-08   |

**Grain:** one row represents one app installation.

### Revenue-event source data

| event_id  | user_install_id | money_value_usd | event_count | event_date |
| --------- | --------------- | --------------: | ----------: | ---------- |
| event_001 | install_001     |            1.25 |           1 | 2024-04-04 |
| event_002 | install_001     |            2.10 |           1 | 2024-04-07 |
| event_003 | install_002     |            0.75 |           1 | 2024-04-25 |

**Grain:** one row represents one revenue event. One installation may appear in several rows.

### Final install-level analytical model

| user_install_id | country | version | network_id | install_date | revenue |
| --------------- | ------- | ------: | ---------: | ------------ | ------: |
| install_001     | US      |     502 |         58 | 2024-04-03   |    3.35 |
| install_002     | FR      |     504 |         60 | 2024-04-24   |    0.75 |
| install_003     | US      |     502 |         58 | 2024-04-08   |    0.00 |

**Grain:** one row per analysed installation, including installations with zero revenue.

---

## Transformation example

Before aggregation, one installation may have multiple revenue events:

```text
install_001
├── $1.25
├── $2.10
└── $0.75
```

After aggregation:

```text
install_001 total revenue = $4.10
```

Final model:

```text
One installation row
+
One aggregated revenue value
=
Correct acquisition and profitability calculations
```

---

## Tableau Dashboard preview

The Tableau dashboard presents:

* Headline profitability metrics
* Network-level profit contribution
* Revenue per install compared with break-even
* Country performance
* App-version performance
* Daily install-cohort performance

<p align="center">
  <a href="https://github.com/Noor-Ahmed-12/mobile-app-analytics-engineering/blob/main/tableau/App%20174%20Performance%20Overview.pdf">
    <img
      src="https://github.com/Noor-Ahmed-12/mobile-app-analytics-engineering/blob/main/tableau/tablaueDsh.png"
      alt="Tableau mobile app performance dashboard"
      width="850"
    >
  </a>
</p>

<p align="center">
  <em>Click the dashboard to open the complete PDF.</em>
</p>

---

## Key visualisations

<table>
  <tr>
    <td align="center" width="50%">
      <img
        src="charts/net_profit_by_network.png"
        alt="Net profit by acquisition network"
        width="420"
      >
      <br>
      <strong>Network profitability</strong>
      <br>
      <sub>Shows which acquisition sources created or reduced total profit.</sub>
    </td>
    <td align="center" width="50%">
      <img
        src="charts/arpi_by_network.png"
        alt="Revenue per install by network"
        width="420"
      >
      <br>
      <strong>Network ARPI versus break-even</strong>
      <br>
      <sub>Compares network unit economics with the break-even threshold.</sub>
    </td>
  </tr>

  <tr>
    <td align="center" width="50%">
      <img
        src="charts/profit_by_country.png"
        alt="Net profit by country"
        width="420"
      >
      <br>
      <strong>Country profitability</strong>
      <br>
      <sub>Highlights substantial monetisation differences between markets.</sub>
    </td>
    <td align="center" width="50%">
      <img
        src="charts/net_profit_by_version.png"
        alt="Net profit by app version"
        width="420"
      >
      <br>
      <strong>App-version profitability</strong>
      <br>
      <sub>Surfaces version-level performance and possible tracking issues.</sub>
    </td>
  </tr>
</table>

### Daily cohort performance

<p align="center">
  <img
    src="charts/daily_trend.png"
    alt="Daily installs and cohort profitability"
    width="720"
  >
</p>

<p align="center">
  <em>
    Late-month cohorts had less time to generate revenue, so their results
    should be interpreted with caution.
  </em>
</p>
