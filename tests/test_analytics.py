import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
import numpy as np
from analytics import kpis, normalize_dataset, forecast_daily_volume


def fixture():
    return pd.DataFrame({
      "Brand":["Freely"]*6,
      "shipment_id":["a","b","c","d","e","f"],
      "manifested_date":pd.to_datetime(["2026-09-01"]*3+["2026-09-02"]*3),
      "manifest_date":pd.to_datetime(["2026-09-01"]*3+["2026-09-02"]*3),
      "shipment_status":["Delivered","RTO Delivered","Cancelled","Delivered","In Transit","RTO Delivered"],
      "courier_name":["X"]*6,"drop_location_state":["MH"]*6,
      "tat":[2,3,np.nan,4,5,6],"attempt_count":[1,2,0,1,1,3],"tat_breached":[0,1,np.nan,0,0,1],
      "est_shipping_charge":[10,20,5,10,12,22],"cod_amount":[0,20,5,0,12,22]
    })


def test_kpi_denominators():
    m=kpis(fixture())
    assert m["total"]==6
    assert m["delivered"]==2 and m["rto"]==2 and m["cancelled"]==1 and m["other"]==1
    assert m["completed"]==4
    assert m["delivery_rate"]==50.0 and m["rto_rate"]==50.0
    assert abs(m["cancellation_share"]-100/6)<1e-9


def test_empty_df_safe():
    d=fixture().iloc[0:0]
    m=kpis(d)
    assert m["total"]==0 and np.isnan(m["delivery_rate"])


def test_normalize_blocks_duplicate_ids():
    raw=pd.DataFrame({"shipment_id":["a","a"],"manifested_date":["2026-09-01","2026-09-02"],"shipment_status":["Delivered","Cancelled"],"courier_name":["X","X"],"drop_location_state":["Maharashtra","MH"]})
    clean,issues=normalize_dataset(raw,"Freely")
    assert len(clean)==2
    assert (issues["severity"]=="error").sum()==2
    assert set(clean["drop_location_state"])=={"MH"}


def test_forecast_nonnegative_and_horizon():
    df=fixture()
    fc=forecast_daily_volume(df,"Freely",5)
    assert len(fc)==5
    assert (fc["Forecast shipments"]>=0).all()
