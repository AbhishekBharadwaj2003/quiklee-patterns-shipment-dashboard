"""Validated analytics helpers for the Quiklee Patterns dashboard.

Metric policy:
- Manifested shipments are counted by manifested_date.
- Outcome rates use only final Delivered and RTO Delivered statuses in the denominator.
- Cancellation share uses all records in the selected cohort as denominator.
- Other/unresolved statuses are shown separately and are never silently classified as failures.
- TAT units are not labelled until confirmed by the business.
"""
from __future__ import annotations
import pandas as pd
import numpy as np

BRANDS = ["Freely", "Kotart", "BigBearFarms"]
DELIVERED = "Delivered"
RTO = "RTO Delivered"
CANCELLED = "Cancelled"
REQUIRED_COLUMNS = ["shipment_id", "manifested_date", "shipment_status", "courier_name", "drop_location_state"]
DATE_COLUMNS = ["invoice_date", "manifested_date", "reached_at_dc_date", "latest_status_date", "first_attempt_date", "pickup_date", "delivery_rto_date", "edd", "pdd", "first_ndr_date", "second_ndr_date", "third_ndr_date", "latest_ndr_date", "first_npr_date", "second_npr_date", "third_npr_date", "latest_npr_date", "rto_initiation_date", "last_attempt_date", "first_pickup_attempt_date", "second_pickup_attempt_date", "third_pickup_attempt_date", "last_pickup_attempt_date"]
STATE_ALIASES = {
    "MAHARASHTRA":"MH", "RAJASTHAN":"RJ", "LADAKH":"LA", "CHANDIGARH":"CH",
    "PUDUCHERRY":"PY", "PONDICHERRY":"PY", "ANDHRA PRADESH":"AP", "KARNATAKA":"KA",
    "TAMIL NADU":"TN", "TELANGANA":"TS", "WEST BENGAL":"WB", "DELHI":"DL",
    "UTTAR PRADESH":"UP", "MADHYA PRADESH":"MP", "GUJARAT":"GJ", "HARYANA":"HR",
    "PUNJAB":"PB", "KERALA":"KL", "ODISHA":"OD", "ORISSA":"OD", "BIHAR":"BR",
    "ASSAM":"AS", "JHARKHAND":"JH", "CHHATTISGARH":"CG", "GOA":"GA",
    "HIMACHAL PRADESH":"HP", "UTTARAKHAND":"UK", "JAMMU AND KASHMIR":"JK",
    "JAMMU & KASHMIR":"JK", "ARUNACHAL PRADESH":"AR", "MEGHALAYA":"ML",
    "MANIPUR":"MN", "MIZORAM":"MZ", "NAGALAND":"NL", "SIKKIM":"SK",
    "TRIPURA":"TR", "ANDAMAN AND NICOBAR ISLANDS":"AN", "LAKSHADWEEP":"LD"
}


def _normalize_text(s: pd.Series, default: str = "Unknown") -> pd.Series:
    out = s.astype("string").str.strip()
    return out.mask(out.eq("") | out.isna(), default)


def normalize_dataset(df: pd.DataFrame, brand: str, source: str = "upload") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize fields and return (cleaned rows, data-quality issue table). Never silently deduplicates."""
    if brand not in BRANDS:
        raise ValueError(f"Unknown brand: {brand}")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    if "shipment_id" not in out:
        raise ValueError("shipment_id is required")
    out["Brand"] = brand
    out["source_file"] = source
    for col in DATE_COLUMNS:
        if col in out.columns:
            # Mixed date formats are handled explicitly to avoid locale-dependent inference.
            try:
                out[col] = pd.to_datetime(out[col], errors="coerce", format="mixed")
            except TypeError:  # pandas < 2.0 compatibility
                out[col] = pd.to_datetime(out[col], errors="coerce")
    for col in ["tat", "attempt_count", "pickup_attempts", "rto_attempts", "est_shipping_charge", "total_amount", "cod_amount", "weight", "est_billing_weight", "tat_breached"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out["shipment_id"] = _normalize_text(out["shipment_id"], "")
    out["shipment_status"] = _normalize_text(out["shipment_status"], "Unknown").str.strip()
    out["courier_name"] = _normalize_text(out["courier_name"], "Unknown")
    out["drop_location_state"] = _normalize_text(out["drop_location_state"], "Unknown").str.upper()
    out["drop_location_state"] = out["drop_location_state"].replace(STATE_ALIASES)
    if "drop_location_city" in out.columns:
        city = _normalize_text(out["drop_location_city"], "Unknown").str.upper()
        fix_pu = out["drop_location_state"].eq("PU") & city.isin(["PONDICHERRY", "PUDUCHERRY"])
        out.loc[fix_pu, "drop_location_state"] = "PY"
    if "payment_type" in out.columns:
        out["payment_type"] = _normalize_text(out["payment_type"], "Unknown").str.upper()
    out["manifest_date"] = out["manifested_date"].dt.normalize()
    issues = []
    for idx, row in out.iterrows():
        sid = row.get("shipment_id", "")
        if not sid:
            issues.append({"row_number": int(idx)+2, "shipment_id":"", "issue":"Missing shipment_id", "severity":"error"})
        if pd.isna(row.get("manifested_date")):
            issues.append({"row_number": int(idx)+2, "shipment_id":sid, "issue":"Missing/invalid manifested_date", "severity":"error"})
        if str(row.get("shipment_status", "Unknown")) == "Unknown":
            issues.append({"row_number": int(idx)+2, "shipment_id":sid, "issue":"Missing shipment_status", "severity":"warning"})
    duplicate_mask = out["shipment_id"].ne("") & out["shipment_id"].duplicated(keep=False)
    for idx in out.index[duplicate_mask]:
        issues.append({"row_number":int(idx)+2, "shipment_id":out.at[idx,"shipment_id"], "issue":"Duplicate shipment_id within uploaded file; review before import", "severity":"error"})
    return out, pd.DataFrame(issues, columns=["row_number","shipment_id","issue","severity"])


def pct(numerator: float, denominator: float):
    return (float(numerator) / float(denominator) * 100.0) if denominator and denominator > 0 else np.nan


def kpis(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"total":0,"delivered":0,"rto":0,"cancelled":0,"other":0,"completed":0,
                "delivery_rate":np.nan,"rto_rate":np.nan,"cancellation_share":np.nan,
                "tat_mean":np.nan,"tat_median":np.nan,"tat_missing":0,"multiple_attempts":0,
                "multiple_attempt_share":np.nan,"tat_breach_count":0,"tat_breach_rate":np.nan,
                "shipping_cost":np.nan,"cost_per_shipment":np.nan,"cod_exposure":np.nan}
    status = df["shipment_status"].astype("string").str.strip()
    total = len(df)
    delivered = int(status.eq(DELIVERED).sum())
    rto = int(status.eq(RTO).sum())
    cancelled = int(status.eq(CANCELLED).sum())
    completed = delivered + rto
    tat = pd.to_numeric(df["tat"], errors="coerce") if "tat" in df else pd.Series(dtype=float)
    attempts = pd.to_numeric(df["attempt_count"], errors="coerce") if "attempt_count" in df else pd.Series(dtype=float)
    breached = pd.to_numeric(df["tat_breached"], errors="coerce") if "tat_breached" in df else pd.Series(dtype=float)
    cost = pd.to_numeric(df["est_shipping_charge"], errors="coerce") if "est_shipping_charge" in df else pd.Series(dtype=float)
    cod = pd.to_numeric(df["cod_amount"], errors="coerce") if "cod_amount" in df else pd.Series(dtype=float)
    other = total - delivered - rto - cancelled
    valid_breach = breached.isin([0,1])
    return {
        "total":total,"delivered":delivered,"rto":rto,"cancelled":cancelled,"other":other,"completed":completed,
        "delivery_rate":pct(delivered,completed),"rto_rate":pct(rto,completed),"cancellation_share":pct(cancelled,total),
        "tat_mean":float(tat.mean()) if tat.notna().any() else np.nan,
        "tat_median":float(tat.median()) if tat.notna().any() else np.nan,
        "tat_missing":int(tat.isna().sum()) if len(tat) else total,
        "multiple_attempts":int((attempts > 1).sum()) if len(attempts) else 0,
        "multiple_attempt_share":pct((attempts > 1).sum(), attempts.notna().sum()) if attempts.notna().any() else np.nan,
        "tat_breach_count":int((breached == 1).sum()) if valid_breach.any() else 0,
        "tat_breach_rate":pct((breached == 1).sum(), valid_breach.sum()) if valid_breach.any() else np.nan,
        "shipping_cost":float(cost.sum(min_count=1)) if cost.notna().any() else np.nan,
        "cost_per_shipment":float(cost.mean()) if cost.notna().any() else np.nan,
        "cod_exposure":float(cod[~status.isin([DELIVERED,RTO,CANCELLED])].sum(min_count=1)) if cod.notna().any() else np.nan,
    }


def brand_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for brand, group in df.groupby("Brand", dropna=False):
        row={"Brand":brand, **kpis(group)}
        rows.append(row)
    return pd.DataFrame(rows)


def courier_summary(df: pd.DataFrame, min_volume: int = 30) -> pd.DataFrame:
    rows=[]
    for (brand,courier), g in df.groupby(["Brand","courier_name"], dropna=False):
        m=kpis(g)
        rows.append({"Brand":brand,"Courier":courier,"Shipments":m["total"],"Delivered":m["delivered"],"RTO":m["rto"],"Cancelled":m["cancelled"],"Other":m["other"],"Completed outcomes":m["completed"],"Delivery rate (%)":m["delivery_rate"],"RTO rate (%)":m["rto_rate"],"Cancellation share (%)":m["cancellation_share"],"Mean TAT (unit unconfirmed)":m["tat_mean"],"Median TAT (unit unconfirmed)":m["tat_median"],"Multiple-attempt share (%)":m["multiple_attempt_share"],"TAT breach rate (%)":m["tat_breach_rate"],"Meets minimum volume":m["total"]>=min_volume})
    return pd.DataFrame(rows)


def state_courier_summary(df: pd.DataFrame, min_volume: int = 10) -> pd.DataFrame:
    rows=[]
    for (brand,state,courier),g in df.groupby(["Brand","drop_location_state","courier_name"],dropna=False):
        m=kpis(g)
        rows.append({"Brand":brand,"State":state,"Courier":courier,"Shipments":m["total"],"Delivered":m["delivered"],"RTO":m["rto"],"Cancelled":m["cancelled"],"Other":m["other"],"Completed outcomes":m["completed"],"Delivery rate (%)":m["delivery_rate"],"RTO rate (%)":m["rto_rate"],"Meets minimum volume":m["total"]>=min_volume})
    return pd.DataFrame(rows)


def daily_manifest_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return pd.DataFrame(columns=["Manifest date","Brand","Shipments"])
    x=df.dropna(subset=["manifest_date"]).groupby(["manifest_date","Brand"]).size().rename("Shipments").reset_index()
    return x.rename(columns={"manifest_date":"Manifest date"}).sort_values("Manifest date")


def recommendation_rules(df: pd.DataFrame, brand: str, selected_date=None) -> list[dict]:
    """Evidence-based deterministic recommendations; no LLM-generated numbers."""
    subset=df[df["Brand"].eq(brand)].copy()
    if selected_date is not None and "manifest_date" in subset:
        subset=subset[subset["manifest_date"].eq(pd.Timestamp(selected_date).normalize())]
    if subset.empty:
        return [{"priority":"Info","title":"Insufficient data for this selection","evidence":"No shipment rows match the selected brand/date.","action":"Choose another date or upload the corresponding dataset."}]
    m=kpis(subset); rec=[]
    if m["completed"] >= 10 and pd.notna(m["rto_rate"]) and m["rto_rate"] >= 15:
        rec.append({"priority":"High","title":"Investigate elevated RTO among completed outcomes","evidence":f"RTO rate is {m['rto_rate']:.1f}% across {m['completed']} completed outcomes ({m['rto']} RTO delivered).","action":"Break down RTO reasons, payment type, destination states, and courier performance before changing allocation."})
    if m["total"] >= 10 and pd.notna(m["cancellation_share"]) and m["cancellation_share"] >= 10:
        rec.append({"priority":"High","title":"Review cancellations","evidence":f"{m['cancelled']} of {m['total']} shipments are cancelled ({m['cancellation_share']:.1f}%).","action":"Inspect cancellation remarks, cancellation timing, and order/payment patterns."})
    if m["total"] >= 10 and pd.notna(m["multiple_attempt_share"]) and m["multiple_attempt_share"] >= 15:
        rec.append({"priority":"Medium","title":"Review repeated delivery attempts","evidence":f"{m['multiple_attempt_share']:.1f}% of records with known attempt counts have more than one attempt.","action":"Inspect NDR reasons, customer availability, address quality, and courier-specific patterns."})
    if "tat_breached" in subset and pd.notna(m["tat_breach_rate"]) and m["tat_breach_rate"] >= 15:
        rec.append({"priority":"Medium","title":"Investigate turnaround-time breaches","evidence":f"{m['tat_breach_rate']:.1f}% of records with a valid TAT breach flag are marked breached.","action":"Review affected couriers and destination states; confirm the business definition of TAT before setting targets."})
    if not rec:
        rec.append({"priority":"Info","title":"No threshold-based alert triggered","evidence":"The available sample did not cross the configured alert thresholds, or there were too few records.","action":"Continue monitoring; absence of an alert is not proof that performance is optimal."})
    return rec


def forecast_daily_volume(df: pd.DataFrame, brand: str, horizon: int = 7) -> pd.DataFrame:
    """Weekday-aware baseline using historical same-weekday averages when supported.

    At least two historical observations for a weekday are required; otherwise
    that date falls back to the recent 7-calendar-day mean. This is a transparent
    baseline, not a validated seasonal forecasting model.
    """
    columns=["Date","Forecast shipments","Method"]
    d=df[df["Brand"].eq(brand)].dropna(subset=["manifest_date"]).copy()
    if d.empty or horizon < 1:
        return pd.DataFrame(columns=columns)
    d["manifest_date"]=pd.to_datetime(d["manifest_date"],errors="coerce").dt.normalize()
    daily=d.dropna(subset=["manifest_date"]).groupby("manifest_date").size().sort_index()
    if daily.empty:
        return pd.DataFrame(columns=columns)
    idx=pd.date_range(daily.index.min(),daily.index.max(),freq="D")
    daily=daily.reindex(idx,fill_value=0).astype(float)
    recent_mean=float(daily.tail(7).mean())
    future=pd.date_range(daily.index.max()+pd.Timedelta(days=1),periods=int(horizon),freq="D")
    rows=[]
    for date in future:
        same_weekday=daily[daily.index.dayofweek==date.dayofweek]
        if len(same_weekday)>=2:
            value=float(same_weekday.tail(8).mean())
            method=f"Same-weekday historical mean ({len(same_weekday.tail(8))} observations)"
        else:
            value=recent_mean
            method="Trailing 7-calendar-day mean fallback (insufficient weekday history)"
        rows.append({"Date":date,"Forecast shipments":round(max(0.0,value),2),"Method":method})
    return pd.DataFrame(rows,columns=columns)
