# Deploy Task 2 (keep this repository private)

This is the **second internship task**: Quiklee Patterns Shipment Analytics. It is separate from the first task repository.

## Important privacy note
The supplied source workbooks can contain customer/order/tracking information. Keep this GitHub repository **Private** and deploy the Streamlit app as **private**. Invite your mentor as a viewer using their email. Do not switch the app/repository to Public unless you first remove sensitive fields and disable raw-row downloads.

## Upload to the separate GitHub repository
Repository: https://github.com/AbhishekBharadwaj2003/quiklee-patterns-shipment-dashboard

Recommended way using GitHub Desktop:
1. Download and extract this deployment ZIP.
2. In GitHub Desktop, choose **File → Clone repository** and clone `AbhishekBharadwaj2003/quiklee-patterns-shipment-dashboard`.
3. Copy the *contents* of the extracted `Quiklee_Task2_Deployment_Package` folder into the cloned repository folder. Confirm the `dashboard.py`, `analytics.py`, `database.py`, `reports.py`, `requirements.txt`, and `data/` folder are at the repository root.
4. Review the changed files. Do **not** add `.venv`, `__pycache__`, `.pytest_cache`, `data/quiklee.db`, or a shipment-level cleaned CSV.
5. Commit with message `Add Task 2 Streamlit shipment dashboard` and click **Push origin**.

## Deploy on Streamlit Community Cloud
1. Open https://share.streamlit.io/ and sign in with the GitHub account that owns this repository.
2. Click **Create app** and select repository `AbhishekBharadwaj2003/quiklee-patterns-shipment-dashboard`, branch `main`, main file path `dashboard.py`.
3. Open **Advanced settings** and choose Python 3.12 if needed.
4. Deploy the app. Verify the app is **private** before sharing.
5. Use the app's **Share** option to invite your mentor's email as a viewer. Share the app URL after the invitation. A private app will require the invited person to authenticate.

## Current limitations
- The chatbot is rule-based, not a generative LLM. Its volume-ranking intent was fixed and checked against the baseline Kotart data: Delhivery = 109 shipments, Ekart = 81, Xpressbees = 8.
- SQLite persistence on hosted ephemeral storage should not be treated as a durable production database. Test uploads and snapshot behavior after deployment; for durable multi-user data, use managed PostgreSQL.
- Automated local checks: `python -m pytest -q` (5 tests) passed after the chatbot fix; focused checks confirmed shipment-count and delivery-rate intents return distinct results.
