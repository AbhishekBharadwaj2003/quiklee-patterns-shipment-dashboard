# Quiklee Patterns Shipment Intelligence Dashboard — Task 2

A Streamlit application for brand-wise shipment analytics, courier/state comparisons, daily uploads and immutable snapshots, rule-based recommendations, a baseline forecast, and PDF/Excel exports. This is **internship Task 2**, separate from Task 1 (`quiklee-shipment-analytics`).

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run dashboard.py
```

## Deploy to Streamlit Community Cloud

1. Keep the associated GitHub repository **Private**. These reference workbooks may contain customer/order/tracking details, and the dashboard supports row-level exports.
2. Upload the project files to `AbhishekBharadwaj2003/quiklee-patterns-shipment-dashboard` (see `DEPLOY_TASK2.md`).
3. At https://share.streamlit.io, create an app from that repo, branch `main`, entrypoint `dashboard.py`; Python 3.12 is a good choice in Advanced settings.
4. Keep the Streamlit app **private** and invite your mentor by email as a viewer. Don't make the app public while it includes sensitive rows/exports.

## What is included

- `dashboard.py`: Streamlit interface, Ask Quiklee and navigation.
- `analytics.py`: data normalization, KPIs, courier/state summaries, recommendations and forecast baseline.
- `database.py`: local SQLite current-state, upload history and immutable snapshots.
- `reports.py`: PDF summary and Excel workbook generation.
- `data/`: source baseline workbooks for Freely, Kotart and BigBearFarms.
- `tests/`: unit tests for analytics and database behavior.

## Accuracy notes

- Delivery rate = Delivered / (Delivered + RTO Delivered). RTO rate uses the same completed-outcome denominator.
- Source workbooks are latest-status extracts. Manifesting-date filtering does not reconstruct historical shipment statuses. Upload snapshots preserve only what was present in each uploaded file.
- Ask Quiklee is rule-based, not a generative LLM. Its volume ranking is intentionally separate from delivery-rate ranking. Against the baseline Kotart dataset it returns Delhivery (109 shipments), Ekart (81), and Xpressbees (8) for shipment-volume queries; delivery-rate queries are separate.
- Forecasting uses a transparent mean baseline, not a validated seasonal model.
- Tests run locally: `python -m pytest -q` (5 passed). A focused check also verified the two chatbot intents separately.

## Hosting limitation

The current SQLite database is stored on the local filesystem. Treat the hosted deployment as a review/demo unless snapshot persistence has been verified across restarts. For durable multi-user use, migrate to a managed database such as PostgreSQL.
