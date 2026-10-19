from io import BytesIO
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from analytics import kpis


def executive_pdf(df: pd.DataFrame, brand_label: str, period_label: str) -> bytes:
    buf=BytesIO(); doc=SimpleDocTemplate(buf,pagesize=landscape(A4),rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=12*mm)
    styles=getSampleStyleSheet(); story=[]
    story.append(Paragraph("Quiklee | Patterns Shipment Performance",styles["Title"]))
    story.append(Paragraph(f"Brand: {brand_label} | Period: {period_label}",styles["Normal"]))
    story.append(Spacer(1,6*mm))
    m=kpis(df)
    rows=[["Metric","Value"], ["Manifested shipment records",str(m['total'])], ["Delivered",str(m['delivered'])], ["RTO Delivered",str(m['rto'])], ["Cancelled",str(m['cancelled'])], ["Other / unresolved statuses",str(m['other'])], ["Delivery rate among completed outcomes", "N/A" if pd.isna(m['delivery_rate']) else f"{m['delivery_rate']:.2f}%"], ["RTO rate among completed outcomes", "N/A" if pd.isna(m['rto_rate']) else f"{m['rto_rate']:.2f}%"], ["Cancellation share of all selected records", "N/A" if pd.isna(m['cancellation_share']) else f"{m['cancellation_share']:.2f}%"], ["Mean TAT (unit unconfirmed)", "N/A" if pd.isna(m['tat_mean']) else f"{m['tat_mean']:.2f}"]]
    t=Table(rows,colWidths=[100*mm,65*mm],repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#14213D')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('GRID',(0,0),(-1,-1),.4,colors.lightgrey),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F4F7FB')]),('PADDING',(0,0),(-1,-1),6)]))
    story.append(t); story.append(Spacer(1,5*mm))
    story.append(Paragraph("Metric definitions and limitations",styles["Heading2"]))
    story.append(Paragraph("Delivery and RTO rates use Delivered + RTO Delivered as the denominator. Cancelled and other statuses are excluded from these completed-outcome rates and shown separately. These rates describe the latest statuses in the selected records, not necessarily historical status as of each manifest date. TAT units have not been confirmed. The report is descriptive and does not establish courier causation.",styles["BodyText"]))
    doc.build(story); return buf.getvalue()


def excel_bytes(sheets: dict[str,pd.DataFrame]) -> bytes:
    buf=BytesIO()
    with pd.ExcelWriter(buf,engine="openpyxl") as writer:
        for name,df in sheets.items():
            safe=name[:31]
            df.to_excel(writer,index=False,sheet_name=safe)
    return buf.getvalue()
