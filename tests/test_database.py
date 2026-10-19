import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import init_db, upsert_current, load_current, import_upload, load_snapshot, upload_history


def sample():
    return pd.DataFrame({"Brand":["Freely","Freely"],"shipment_id":["s1","s2"],"manifested_date":pd.to_datetime(["2026-09-01","2026-09-02"]),"manifest_date":pd.to_datetime(["2026-09-01","2026-09-02"]),"shipment_status":["Delivered","In Transit"],"courier_name":["BlueDart","BlueDart"],"drop_location_state":["MH","KA"]})


def test_db_upsert_snapshot_and_duplicate_import(tmp_path):
    db=tmp_path/"test.db"
    init_db(db)
    df=sample()
    assert upsert_current(df,db)==2
    assert len(load_current(db))==2
    payload=b"identical-content"
    first=import_upload(df,"Freely","2026-10-01","daily.csv",payload,0,db)
    second=import_upload(df,"Freely","2026-10-01","daily.csv",payload,0,db)
    assert first["duplicate_upload"] is False
    assert second["duplicate_upload"] is True
    assert len(load_snapshot("2026-10-01",db_path=db))==2
    assert len(upload_history(db))==1
