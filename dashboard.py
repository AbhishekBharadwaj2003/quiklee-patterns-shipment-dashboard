from pathlib import Path
from io import BytesIO
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from analytics import BRANDS, normalize_dataset, kpis, brand_summary, courier_summary, state_courier_summary, daily_manifest_summary, recommendation_rules, forecast_daily_volume
from database import init_db, upsert_current, load_current, load_snapshot, import_upload, upload_history
from reports import executive_pdf, excel_bytes

BASE=Path(__file__).resolve().parent
DATA_DIR=BASE/"data"
SEED_FILES={"Freely":DATA_DIR/"freely_patterns.xlsx","Kotart":DATA_DIR/"kotart_patterns.xlsx","BigBearFarms":DATA_DIR/"bigbearfarms_patterns.xlsx"}

st.set_page_config(page_title="Quiklee | Patterns Intelligence",page_icon="📦",layout="wide",initial_sidebar_state="expanded")
st.markdown("""<style>
.block-container{padding-top:1.3rem;padding-bottom:2rem}
[data-testid="stSidebar"]{border-right:1px solid rgba(120,130,150,.2)}
.kicker{color:#64748b;font-size:.82rem;text-transform:uppercase;letter-spacing:.08em}
</style>""",unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def read_seed(path: str, brand: str):
    raw=pd.read_excel(path)
    clean,issues=normalize_dataset(raw,brand,Path(path).name)
    return clean,issues


def bootstrap():
    init_db()
    current=load_current()
    if current.empty:
        pieces=[]
        for brand,path in SEED_FILES.items():
            if not path.exists(): raise FileNotFoundError(f"Seed dataset missing: {path}")
            df,_=read_seed(str(path),brand); pieces.append(df)
        seeded=pd.concat(pieces,ignore_index=True)
        # The supplied files are baseline extracts, not dated historical snapshots.
        upsert_current(seeded)


def current_data():
    bootstrap()
    df=load_current()
    if df.empty: return df
    if "manifest_date" not in df.columns:
        df["manifest_date"]=pd.to_datetime(df["manifested_date"],errors="coerce").dt.normalize()
    else: df["manifest_date"]=pd.to_datetime(df["manifest_date"],errors="coerce").dt.normalize()
    return df

try:
    data=current_data()
except Exception as e:
    st.error(f"Could not initialize the dashboard: {e}"); st.stop()

# Main dashboard header: Quiklee symbol + wordmark
mark_path = BASE / "data" / "QUIKLEE_MARK.png"
logo_path = BASE / "data" / "QUIKLEE_LOGO.jpg"
header_brand, header_title = st.columns([1.35, 2.65], vertical_alignment="center")
with header_brand:
    mark_col, word_col = st.columns([1, 2.4], vertical_alignment="center")
    with mark_col:
        if mark_path.exists():
            st.image(str(mark_path), use_container_width=True)
    with word_col:
        if logo_path.exists():
            st.image(str(logo_path), use_container_width=True)
        else:
            st.markdown("## QUIKLEE")
            st.caption("FUTURE STORES")
with header_title:
    st.title("Patterns Shipment Intelligence")
    st.caption("Freely · Kotart · BigBearFarms")

st.divider()

with st.sidebar:
    st.markdown("# 📦 Quiklee")
    st.caption("Patterns shipment intelligence")
    st.divider()
    page=st.radio("Navigation",["Executive Overview","Brand Analysis","Courier Performance","State-wise Analysis","AI Recommendations","Forecasting","Dataset Upload & Reports"],label_visibility="collapsed")
    st.divider()
    brands_available=[b for b in BRANDS if b in set(data.get("Brand",pd.Series(dtype=str)).dropna())]
    selected_brands=st.multiselect("Brands",brands_available,default=brands_available)
    date_basis=st.selectbox("Date view",["Manifesting date","Uploaded snapshot date"],help="Manifesting date filters shipment cohorts. Uploaded snapshot date shows the exact records stored for that upload date.")
    if date_basis=="Manifesting date":
        date_values=sorted(pd.to_datetime(data.get("manifest_date",pd.Series(dtype="datetime64[ns]")),errors="coerce").dropna().dt.normalize().unique())
        date_options=["All dates"]+[pd.Timestamp(d).strftime("%Y-%m-%d") for d in date_values]
        selected_date_label=st.selectbox("Date",date_options,index=0)
        selected_date=None if selected_date_label=="All dates" else pd.Timestamp(selected_date_label)
    else:
        hist_dates=[]
        hist=upload_history()
        if not hist.empty: hist_dates=sorted(hist["reporting_date"].dropna().astype(str).unique(),reverse=True)
        if hist_dates:
            selected_date_label=st.selectbox("Uploaded reporting date",hist_dates,index=0)
            selected_date=pd.Timestamp(selected_date_label)
        else:
            selected_date_label="No uploaded snapshots"; selected_date=None
            st.caption("Upload a daily dataset to enable snapshot-date analysis.")
    st.caption("Snapshot dates show the uploaded file as stored. Manifesting-date views group by manifested_date and use the latest statuses available in the extract.")
    st.divider()
    with st.expander(
        "💬 Ask Quiklee",
        expanded=st.session_state.get("quiklee_answer_requested", False),
    ):
        question=st.text_input(
            "Ask about the selected data",
            key="quiklee_question_input",
            placeholder="e.g. best courier for Kotart",
        )
        ask_col, clear_col = st.columns(2)
        with ask_col:
            ask_clicked = st.button("Ask",key="ask_quiklee",use_container_width=True)
        with clear_col:
            clear_clicked = st.button("Clear",key="clear_quiklee",use_container_width=True)
        if ask_clicked:
            st.session_state["quiklee_question"]=question
            st.session_state["quiklee_answer_requested"]=True
        if clear_clicked:
            st.session_state["quiklee_question"]=""
            st.session_state["quiklee_question_input"]=""
            st.session_state["quiklee_answer_requested"]=False

analysis_data=data
if date_basis=="Uploaded snapshot date" and selected_date is not None:
    analysis_data=load_snapshot(selected_date)
    if analysis_data.empty:
        st.warning("No snapshot records were found for the selected reporting date.")
    if "manifest_date" not in analysis_data.columns and "manifested_date" in analysis_data.columns:
        analysis_data["manifest_date"]=pd.to_datetime(analysis_data["manifested_date"],errors="coerce").dt.normalize()
filtered=analysis_data[analysis_data["Brand"].isin(selected_brands)].copy() if selected_brands and "Brand" in analysis_data else analysis_data.iloc[0:0].copy()
if date_basis=="Manifesting date" and selected_date is not None:
    filtered=filtered[filtered["manifest_date"].eq(selected_date)]


def rate_text(v): return "N/A" if pd.isna(v) else f"{v:.2f}%"
def show_day_over_day(current_df, previous_df):
    """Compact KPI cards with previous-day deltas."""
    current = kpis(current_df)
    previous = kpis(previous_df)

    def count_delta(now, before):
        if pd.isna(now) or pd.isna(before):
            return None
        if before == 0:
            return "New vs prev day" if now > 0 else "0.0% vs prev day"
        return f"{(now - before) / abs(before) * 100:+.1f}% vs prev day"

    specs = [
        ("📦 Total shipments", "total", "normal", False),
        ("✅ Delivered", "delivered", "normal", False),
        ("↩️ RTO delivered", "rto", "inverse", False),
        ("❌ Cancelled", "cancelled", "inverse", False),
        ("📈 Delivery rate", "delivery_rate", "normal", True),
        ("📉 RTO rate", "rto_rate", "inverse", True),
    ]
    cols = st.columns(6)
    for col, (label, key, direction, is_rate) in zip(cols, specs):
        now, before = current[key], previous[key]
        value = "N/A" if pd.isna(now) else (f"{now:.2f}%" if is_rate else f"{int(now):,}")
        if pd.isna(now) or pd.isna(before):
            delta = None
        elif is_rate:
            delta = f"{now - before:+.2f} pp vs prev day"
        else:
            delta = count_delta(now, before)
        col.metric(label, value, delta=delta, delta_color=direction)

def show_kpis(df):
    m=kpis(df); cols=st.columns(6)
    items=[("Manifested",m["total"]),("Delivered",m["delivered"]),("RTO Delivered",m["rto"]),("Cancelled",m["cancelled"]),("Delivery rate*",rate_text(m["delivery_rate"])),("RTO rate*",rate_text(m["rto_rate"]))]
    for c,(label,value) in zip(cols,items): c.metric(label,value)
    st.caption("* Delivery/RTO rate denominator = Delivered + RTO Delivered. Cancellation and other statuses are excluded from these rates.")


def download_buttons(df,brand_label,period_label,prefix="quiklee"):
    st.download_button("Download cleaned CSV",df.to_csv(index=False).encode("utf-8-sig"),file_name=f"{prefix}_cleaned.csv",mime="text/csv")
    st.download_button("Download executive PDF",executive_pdf(df,brand_label,period_label),file_name=f"{prefix}_executive_summary.pdf",mime="application/pdf")


def chatbot_answer(q, df):
    """Deterministic Q&A over the already-filtered shipment data."""
    if not isinstance(q, str) or not q.strip():
        return "Enter a question first."

    ql=q.lower().strip()
    answer_df=df.copy()

    # If a brand is explicitly named, narrow to that brand while preserving date filters.
    if "Brand" in answer_df.columns:
        mentioned=[b for b in BRANDS if b.lower() in ql]
        if mentioned:
            answer_df=answer_df[answer_df["Brand"].eq(mentioned[0])].copy()
            if answer_df.empty:
                return f"No {mentioned[0]} records are available under the current date/snapshot selection. Change the date or upload a matching snapshot."

    if answer_df.empty:
        return "There are no records for the current filters. Select a brand/date or upload data."

    scope="current selection"
    if "Brand" in answer_df.columns and answer_df["Brand"].nunique()==1:
        scope=str(answer_df["Brand"].iloc[0])

    # Shipment-volume intent must be handled before general courier/ranking intent.
    # Otherwise a question like "which courier has the highest shipments" is
    # incorrectly answered using delivery-rate ranking.
    shipment_count_intent = any(phrase in ql for phrase in [
        "highest shipments", "most shipments", "maximum shipments",
        "max shipments", "highest number of shipments", "most number of shipments",
        "largest shipment count", "maximum shipment count", "highest shipment count",
        "shipments by courier", "shipment count by courier", "courier with most",
        "courier has the most", "courier has highest shipments",
        "courier with highest shipments", "which courier has the highest shipments",
    ])
    if shipment_count_intent:
        if "courier_name" not in answer_df.columns:
            return "Courier data is not available in this selection."
        counts=(answer_df.assign(courier_name=answer_df["courier_name"].fillna("Unknown").astype(str).str.strip())
                .groupby("courier_name",dropna=False).size().sort_values(ascending=False))
        counts=counts[counts.index != ""]
        if counts.empty:
            return f"No courier shipment counts are available for {scope} under the current filters."
        top_count=int(counts.iloc[0])
        top_couriers=counts[counts.eq(top_count)].index.tolist()
        if len(top_couriers)==1:
            return f"Courier with the highest shipment count for {scope}: {top_couriers[0]} ({top_count} shipments) under the current date/snapshot filters. This is a shipment-volume ranking, not a delivery-rate ranking."
        return f"Tie for highest shipment count for {scope}: " + "; ".join(f"{name} ({top_count} shipments)" for name in top_couriers) + ". This is a shipment-volume ranking, not a delivery-rate ranking."

    m=kpis(answer_df)

    # Recommendations should be checked before broad words like 'best' or 'improve'.
    if any(x in ql for x in ["recommend", "recommendation", "improve", "suggestion", "what should"]):
        brands=answer_df["Brand"].dropna().unique().tolist() if "Brand" in answer_df.columns else []
        if not brands:
            return "I can't identify the brand for recommendations from this selection. Select a brand and try again."
        recs=[]
        for brand in brands:
            recs.extend(recommendation_rules(answer_df,brand,selected_date))
        if not recs:
            return f"No rule-based recommendations were triggered for {scope} in this selection. This does not mean there are no operational issues."
        return "\n\n".join([f"{r['priority']}: {r['title']}\nEvidence: {r['evidence']}\nAction: {r['action']}" for r in recs])

    if any(x in ql for x in ["state", "states"]):
        sc=state_courier_summary(answer_df,min_volume=5)
        sc=sc[sc["Meets minimum volume"] & sc["Delivery rate (%)"].notna()].sort_values(["Delivery rate (%)","Shipments"],ascending=[False,False])
        if sc.empty:
            return "No state-courier groups meet the minimum sample threshold for this selection."
        return f"Top state-courier combinations for {scope} by observed completed-outcome delivery rate:\n"+"\n".join([f"{r.State} — {r.Courier}: {r['Delivery rate (%)']:.1f}% ({int(r.Shipments)} shipments)" for _,r in sc.head(5).iterrows()])+"\nTreat low-volume results cautiously."

    if "courier" in ql or any(x in ql for x in ["best", "rank", "ranking"]):
        cs=courier_summary(answer_df,min_volume=10)
        cs=cs[(cs["Meets minimum volume"]) & cs["Delivery rate (%)"].notna()]
        if cs.empty:
            return "There are not enough completed outcomes to rank couriers reliably in this selection. Try a broader date range or lower minimum-volume threshold in Courier Performance."
        cs=cs.sort_values(["Delivery rate (%)","RTO rate (%)","Shipments"],ascending=[False,True,False])
        r=cs.iloc[0]
        return f"Highest observed completed-outcome delivery rate for {scope}: {r['Courier']} ({r['Delivery rate (%)']:.2f}%, {int(r['Shipments'])} shipments, {int(r['Completed outcomes'])} completed outcomes). This is a descriptive ranking, not proof of courier causation; compare like-for-like states and shipment mix before operational changes."

    if any(x in ql for x in ["delivery rate", "rto rate", "cancel", "how many", "shipment", "manifest", "delivered", "status", "summary", "summarize", "summarise", "count", "total"]):
        return f"Summary for {scope} under the current date/snapshot filters: {m['total']} shipment records; {m['delivered']} Delivered; {m['rto']} RTO Delivered; {m['cancelled']} Cancelled; {m['other']} other statuses. Delivery rate among completed outcomes: {rate_text(m['delivery_rate'])}; RTO rate among completed outcomes: {rate_text(m['rto_rate'])}; cancellation share of all records: {rate_text(m['cancellation_share'])}."

    return "I can answer shipment/status counts, delivery and RTO rates, courier rankings, state-courier comparisons, and rule-based recommendations. Try: 'summarize Freely', 'best courier for Kotart', 'show state courier performance', or 'recommend improvements'. This is a local rule-based assistant, not a generative AI model."


if page=="Executive Overview":
    st.subheader("Executive overview")
    if date_basis == "Manifesting date" and selected_date is not None:
        comparison_base = analysis_data[
            analysis_data["Brand"].isin(selected_brands)
        ].copy() if selected_brands and "Brand" in analysis_data else analysis_data.iloc[0:0].copy()
        comparison_base["manifest_date"] = pd.to_datetime(comparison_base["manifest_date"], errors="coerce").dt.normalize()
        previous_date = selected_date - pd.Timedelta(days=1)
        current_day = comparison_base[comparison_base["manifest_date"].eq(selected_date)]
        previous_day = comparison_base[comparison_base["manifest_date"].eq(previous_date)]
        show_day_over_day(current_day, previous_day)
    show_kpis(filtered)
    left,right=st.columns([1.4,1])
    with left:
        daily=daily_manifest_summary(filtered)
        if not daily.empty:
            fig=px.line(daily,x="Manifest date",y="Shipments",color="Brand",markers=True,title="Daily manifested shipment volume")
            st.plotly_chart(fig,use_container_width=True)
    with right:
        if not filtered.empty:
            counts=filtered["shipment_status"].value_counts().rename_axis("Status").reset_index(name="Shipments")
            st.plotly_chart(px.pie(counts,names="Status",values="Shipments",hole=.55,title="Latest status mix in selected records"),use_container_width=True)
    st.subheader("Brand-wise KPI comparison")
    bs=brand_summary(filtered)
    if not bs.empty:
        display=bs.rename(columns={"total":"Shipments","delivered":"Delivered","rto":"RTO Delivered","cancelled":"Cancelled","other":"Other statuses","delivery_rate":"Delivery rate (%)","rto_rate":"RTO rate (%)","cancellation_share":"Cancellation share (%)"})
        st.dataframe(display,use_container_width=True,hide_index=True)
    st.subheader("Data quality flags")
    flags=[]
    for brand in selected_brands:
        try:
            src=filtered[filtered["Brand"].eq(brand)]
            flags.append({"Brand":brand,"Rows":len(src),"Missing shipment ID":int(src["shipment_id"].isna().sum() if "shipment_id" in src else len(src)),"Missing manifest date":int(src["manifest_date"].isna().sum()),"Missing TAT":int(pd.to_numeric(src.get("tat",pd.Series(index=src.index,dtype=float)),errors="coerce").isna().sum()),"Unknown courier":int(src["courier_name"].eq("Unknown").sum())})
        except Exception: pass
    st.dataframe(pd.DataFrame(flags),use_container_width=True,hide_index=True)

elif page=="Brand Analysis":
    st.subheader("Brand performance")
    brand=st.selectbox("Select brand",selected_brands or BRANDS)
    df=filtered[filtered["Brand"].eq(brand)].copy()
    show_kpis(df)
    if df.empty: st.info("No rows for the selected brand/date.")
    else:
        daily=daily_manifest_summary(df)
        a,b=st.columns(2)
        with a: st.plotly_chart(px.bar(daily,x="Manifest date",y="Shipments",title=f"{brand}: daily manifesting"),use_container_width=True)
        with b:
            status=df["shipment_status"].value_counts().rename_axis("Status").reset_index(name="Shipments")
            st.plotly_chart(px.bar(status,x="Status",y="Shipments",title="Latest shipment status counts"),use_container_width=True)
        st.markdown("#### Courier breakdown")
        st.dataframe(courier_summary(df),use_container_width=True,hide_index=True)
        st.markdown("#### State breakdown")
        state=state_courier_summary(df)
        st.dataframe(state.sort_values(["State","Shipments"],ascending=[True,False]),use_container_width=True,hide_index=True)
        if "rto_reason" in df:
            reasons=df.loc[df["shipment_status"].eq("RTO Delivered"),"rto_reason"].dropna().astype(str).str.strip()
            reasons=reasons[reasons.ne("")].value_counts().head(10).rename_axis("RTO reason").reset_index(name="Count")
            if not reasons.empty: st.plotly_chart(px.bar(reasons,x="Count",y="RTO reason",orientation="h",title="Top recorded RTO reasons"),use_container_width=True)
        download_buttons(df,brand,selected_date_label,brand.lower())

elif page=="Courier Performance":
    st.subheader("Courier performance by brand")
    min_volume=st.number_input("Minimum shipment count to qualify for ranking",min_value=1,max_value=500, value=30,step=1)
    cs=courier_summary(filtered,int(min_volume))
    if cs.empty: st.info("No courier data available for these filters.")
    else:
        eligible=cs[cs["Meets minimum volume"]].copy()
        if not eligible.empty:
            st.plotly_chart(px.bar(eligible,x="Courier",y="Delivery rate (%)",color="Brand",barmode="group",title="Delivery rate among completed outcomes (eligible couriers only)"),use_container_width=True)
        st.dataframe(cs.sort_values(["Brand","Delivery rate (%)"],ascending=[True,False]),use_container_width=True,hide_index=True)
        st.caption("Rankings are descriptive. Compare couriers within the same brand/state and consider shipment mix, volume, and unresolved statuses.")
        st.download_button("Download courier CSV",cs.to_csv(index=False).encode("utf-8-sig"),"courier_performance.csv","text/csv")

elif page=="State-wise Analysis":
    st.subheader("State-wise courier comparison")
    min_volume=st.number_input("Minimum shipments per brand-state-courier group",min_value=1,max_value=500,value=10,step=1)
    sc=state_courier_summary(filtered,int(min_volume))
    if not sc.empty:
        eligible=sc[sc["Meets minimum volume"] & sc["Delivery rate (%)"].notna()]
        st.dataframe(sc.sort_values(["Brand","State","Delivery rate (%)"],ascending=[True,True,False]),use_container_width=True,hide_index=True)
        if not eligible.empty:
            chosen_brand=st.selectbox("Heatmap brand",sorted(eligible["Brand"].unique()))
            h=eligible[eligible["Brand"].eq(chosen_brand)].pivot_table(index="State",columns="Courier",values="Delivery rate (%)",aggfunc="first")
            st.plotly_chart(px.imshow(h,labels=dict(x="Courier",y="State",color="Delivery rate (%)"),aspect="auto",color_continuous_scale="Blues",title=f"{chosen_brand}: delivery rate by state and courier"),use_container_width=True)
        st.caption("Groups below the selected minimum volume remain visible in the table but are excluded from the heatmap/ranking view.")
        st.download_button("Download state-courier CSV",sc.to_csv(index=False).encode("utf-8-sig"),"state_courier_analysis.csv","text/csv")

elif page=="AI Recommendations":
    st.subheader("Daily operational recommendations")
    if not selected_brands: st.warning("Select at least one brand in the sidebar.")
    for brand in selected_brands:
        st.markdown(f"### {brand}")
        recs=recommendation_rules(analysis_data,brand,selected_date if date_basis=="Manifesting date" else None)
        for rec in recs:
            with st.container(border=True):
                st.markdown(f"**{rec['priority']} · {rec['title']}**")
                st.write(rec["evidence"]); st.write("**Suggested action:** "+rec["action"])
    st.caption("Recommendations are deterministic KPI rules, not proof of cause. Thresholds are initial defaults and should be reviewed with Quiklee operations.")

elif page=="Forecasting":
    st.subheader("Shipment volume forecast")
    brand=st.selectbox("Forecast brand",selected_brands or BRANDS)
    horizon=st.slider("Forecast horizon (days)",min_value=3,max_value=14,value=7)
    historical=data[data["Brand"].eq(brand)].dropna(subset=["manifest_date"]).groupby("manifest_date").size().rename("Actual shipments").reset_index().rename(columns={"manifest_date":"Date"})
    future=forecast_daily_volume(data,brand,horizon)
    a,b=st.columns([1.4,1])
    with a:
        if not historical.empty: st.plotly_chart(px.line(historical,x="Date",y="Actual shipments",markers=True,title="Historical daily manifest volume"),use_container_width=True)
        if not future.empty: st.plotly_chart(px.line(future,x="Date",y="Forecast shipments",markers=True,title="Weekday-aware baseline forecast"),use_container_width=True)
    with b:
        st.markdown("#### Forecast output"); st.dataframe(future,use_container_width=True,hide_index=True)
        st.info("Forecasts use historical averages for the same weekday when at least two observations are available; otherwise they fall back to the recent 7-calendar-day mean. The dataset covers only about one month, so this is an interpretable baseline—not a validated seasonal model. Check data-quality spikes and evaluate forecast error as more daily data arrives.")
        st.download_button("Download forecast CSV",future.to_csv(index=False).encode("utf-8-sig"),"shipment_forecast.csv","text/csv")

elif page=="Dataset Upload & Reports":
    st.subheader("Upload daily dataset")
    st.warning("Choose the date the file represents. The upload is stored as an immutable snapshot and its shipment IDs update the current-state table. A reporting date does not automatically reconstruct historical statuses unless the file truly represents that snapshot.")
    with st.form("upload_form",clear_on_submit=False):
        brand=st.selectbox("Brand",BRANDS)
        report_date=st.date_input("Dataset reporting date",value=pd.Timestamp("2026-09-30").date())
        file=st.file_uploader("Upload Excel or CSV",type=["xlsx","xls","csv"])
        allow_issues=st.checkbox("Allow import when warnings exist (errors are always blocked)",value=False)
        submitted=st.form_submit_button("Validate and import",type="primary")
    if submitted:
        if file is None: st.error("Select a file first.")
        else:
            try:
                raw=pd.read_csv(file) if file.name.lower().endswith(".csv") else pd.read_excel(file)
                clean,issues=normalize_dataset(raw,brand,file.name)
                st.session_state["last_upload_issues"]=issues
                errors=issues[issues["severity"].eq("error")] if not issues.empty else issues
                if not issues.empty: st.dataframe(issues,use_container_width=True,hide_index=True)
                if not errors.empty: st.error("Import blocked: fix all error-level data-quality issues first.")
                elif not issues.empty and not allow_issues: st.warning("Warnings exist. Review them and tick the allow-warnings option to proceed.")
                else:
                    result=import_upload(clean,brand,report_date,file.name,file.getvalue(),len(issues))
                    if result["duplicate_upload"]: st.warning("This exact file was already imported for this brand and reporting date. No duplicate import was made.")
                    else:
                        st.success(f"Imported {result['imported_count']} rows. Database updated.")
                        st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"Upload validation failed: {e}")
    st.markdown("### Upload history")
    hist=upload_history()
    if hist.empty: st.info("No daily uploads yet. The three reference workbooks are loaded as the initial baseline.")
    else: st.dataframe(hist,use_container_width=True,hide_index=True)
    st.markdown("### Download reports")
    show_kpis(filtered)
    period=selected_date_label
    download_buttons(filtered,"All selected brands" if len(selected_brands)!=1 else selected_brands[0],period,"quiklee")
    cleaned_csv=filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Download selected data as CSV",cleaned_csv,"quiklee_selected_cleaned.csv","text/csv")
    st.download_button("Download analysis workbook (Excel)",excel_bytes({"Cleaned data":filtered,"Brand summary":brand_summary(filtered),"Courier performance":courier_summary(filtered),"State courier":state_courier_summary(filtered),"Upload history":hist}),"quiklee_analysis.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if st.session_state.get("quiklee_answer_requested"):
    q=st.session_state.get("quiklee_question","")
    with st.sidebar:
        st.markdown("**Quiklee's answer**")
        st.info(chatbot_answer(q,filtered))
    st.session_state["quiklee_answer_requested"]=False

with st.expander("Metric definitions and known limitations"):
    st.markdown("""- **Delivery rate:** Delivered / (Delivered + RTO Delivered).
- **RTO rate:** RTO Delivered / (Delivered + RTO Delivered).
- **Cancellation share:** Cancelled / all selected shipment records.
- **Other statuses:** All statuses other than Delivered, RTO Delivered, and Cancelled. These are not assumed to be final outcomes.
- **Daily manifesting:** Grouped by `manifested_date`, not status date.
- **Historical status limitation:** The source files are latest-status extracts. They cannot prove what status a shipment had on a prior date. Uploaded snapshots are preserved separately.
- **TAT:** Unit and exact business definition are unconfirmed; the dashboard deliberately does not label it hours/days.
- **Forecast:** Weekday-aware historical mean with a recent 7-day fallback when weekday history is sparse; this is a baseline, not a validated seasonal model.
- **Courier comparisons:** Descriptive; volume thresholds reduce but do not eliminate small-sample instability or shipment-mix bias.
""")
