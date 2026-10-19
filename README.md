# Quiklee Patterns Shipment Analytics Dashboard — Task 2

A Streamlit application for shipment analytics across Freely, Kotart, and BigBearFarms. This is **internship Task 2** and is separate from the first-task repository `quiklee-shipment-analytics`.

## Deployment

Entrypoint: `dashboard.py`  
Dependencies: `requirements.txt`  
Recommended host: Streamlit Community Cloud.

Keep this repository **Private**. The reference workbooks can contain sensitive shipment/customer details and the dashboard supports row-level exports. Deploy as a private Streamlit app and invite your mentor as a viewer, rather than making this repository or app public.

## Main modules
- `dashboard.py`: Streamlit UI and Ask Quiklee.
- `analytics.py`: normalization, KPI definitions, courier/state summaries, recommendations, forecast baseline.
- `database.py`: SQLite current-state records and immutable upload snapshots.
- `reports.py`: PDF and Excel exports.
- `data/`: September 2026 reference workbooks.

## Local checks
Run `python -m pytest -q` (5 tests). Ask Quiklee currently uses deterministic rule-based intent matching rather than a generative LLM. The shipment-count intent has been corrected and checked separately from delivery-rate ranking.

## Hosting limitation
The SQLite file is stored locally under `data/`. Do not rely on hosted local-disk storage for durable historical snapshots across redeployments. For persistent multi-user use, migrate to a managed database such as PostgreSQL.
