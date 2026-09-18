#!/usr/bin/env python3
"""
Normalize /exam/data/sales into deterministic, partitioned Parquet in MinIO.

Important design decisions from billing_notes.md:
- filename date is business_date; do not derive it from timestamp
- S06-S09 use semicolon and different column names
- S10-S12 timestamps are epoch seconds UTC and files have UTF-8 BOM
- re-sends are NOT chosen as newest; union all files and de-duplicate by
  (bill_no,line_no)
- keep VOID rows; they cancel the corresponding SALE rows
"""
from pathlib import Path
import io, os, re, hashlib
import pandas as pd
import boto3
from botocore.client import Config

SALES_DIR = Path(os.environ.get("SALES_DIR", "/exam/data/sales"))
BUCKET = os.environ.get("S3_BUCKET", "annapurna")
ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:9000")
KEY = os.environ.get("S3_ACCESS_KEY", "minioadmin")
SECRET = os.environ.get("S3_SECRET_KEY", "minioadmin")

pat = re.compile(r"^SALES_(S\d{2})_(\d{8})(?:__R\d+)?\.(csv|parquet)$", re.I)

ALIASES = {
    "bill_no": ["bill_no", "billnumber", "bill_number"],
    "line_no": ["line_no", "lineno", "line_number"],
    "product_code": ["product_code", "item_code", "itemcode"],
    "qty": ["qty", "quantity"],
    "unit_price": ["unit_price", "rate"],
    "line_type": ["line_type", "type"],
    "ts": ["ts", "txn_time", "timestamp"],
}

def canonicalize(df, store, business_date):
    df.columns = [str(c).replace("\ufeff","").strip().lower() for c in df.columns]
    rename = {}
    for target, choices in ALIASES.items():
        for c in choices:
            if c in df.columns:
                rename[c] = target
                break
    df = df.rename(columns=rename)
    missing = [c for c in ALIASES if c not in df.columns]
    if missing:
        raise ValueError(f"{store} {business_date}: missing columns {missing}; got {list(df.columns)}")

    out = df[["bill_no","line_no","product_code","qty","unit_price","line_type","ts"]].copy()
    out["bill_no"] = out["bill_no"].astype(str)
    out["line_no"] = pd.to_numeric(out["line_no"], errors="raise").astype("int64")
    out["product_code"] = out["product_code"].astype(str)
    out["qty"] = pd.to_numeric(out["qty"], errors="raise")
    out["unit_price"] = pd.to_numeric(out["unit_price"], errors="raise")
    out["line_type"] = out["line_type"].astype(str).str.upper().str.strip()

    if store >= "S10":
        out["ts"] = pd.to_datetime(pd.to_numeric(out["ts"], errors="raise"),
                                   unit="s", utc=True, errors="coerce")
    else:
        # S06-S09 are dd-mm-yyyy; dayfirst is harmless for ISO strings.
        out["ts"] = pd.to_datetime(out["ts"], dayfirst=(store >= "S06" and store <= "S09"),
                                   errors="coerce")

    out["store_id"] = store
    out["business_date"] = pd.to_datetime(business_date).date()
    out["source_file"] = ""
    return out

def read_file(path, store, business_date):
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        sep = ";" if "S06" <= store <= "S09" else ","
        df = pd.read_csv(path, sep=sep, encoding="utf-8-sig")
    return canonicalize(df, store, business_date)

def s3_client():
    return boto3.client("s3", endpoint_url=ENDPOINT,
                        aws_access_key_id=KEY, aws_secret_access_key=SECRET,
                        config=Config(signature_version="s3v4"), region_name="us-east-1")

def ensure_bucket(s3):
    try:
        s3.head_bucket(Bucket=BUCKET)
    except Exception:
        s3.create_bucket(Bucket=BUCKET)

def checksum(df):
    cols=["bill_no","line_no","store_id","business_date","product_code","qty","unit_price","line_type"]
    x=df[cols].astype(str).sort_values(["bill_no","line_no"]).to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(x.encode()).hexdigest()

def main():
    if not SALES_DIR.exists():
        raise SystemExit(f"Sales directory not found: {SALES_DIR}")
    paths=[p for p in SALES_DIR.iterdir() if p.is_file() and pat.match(p.name)]
    if not paths:
        raise SystemExit(f"No SALES_* files found under {SALES_DIR}")
    groups={}
    for p in sorted(paths):
        m=pat.match(p.name)
        store, ds, ext=m.group(1), m.group(2), m.group(3)
        groups.setdefault((store,ds), []).append(p)

    s3=s3_client(); ensure_bucket(s3)
    total_raw=total_dupes=0
    manifest=[]

    for (store,ds), files in sorted(groups.items()):
        frames=[]
        for p in files:
            x=read_file(p,store,ds)
            x["source_file"]=p.name
            frames.append(x)
        allx=pd.concat(frames, ignore_index=True)
        raw=len(allx)
        total_raw += raw
        # Deterministic line-level idempotency. Resends may be partial, so union
        # all resend files before dropping duplicate line keys.
        allx=allx.sort_values(["bill_no","line_no","source_file"], kind="mergesort")
        dupes=allx.duplicated(["bill_no","line_no"]).sum()
        total_dupes += int(dupes)
        allx=allx.drop_duplicates(["bill_no","line_no"], keep="first").copy()

        # Resolve product later in DuckDB/Postgres; keep canonical raw columns here.
        out=allx[["bill_no","line_no","store_id","business_date",
                  "product_code","qty","unit_price","line_type","ts"]]
        buf=io.BytesIO()
        out.to_parquet(buf,index=False,compression="snappy")
        key=f"sales/store_id={store}/business_date={ds[:4]}-{ds[4:6]}-{ds[6:]}/data.parquet"
        s3.put_object(Bucket=BUCKET,Key=key,Body=buf.getvalue())
        manifest.append((store,ds,len(files),raw,int(dupes),len(out),len(buf.getvalue()),checksum(out)))
    print(f"groups={len(manifest)} raw_rows={total_raw} duplicate_lines_removed={total_dupes}")
    print("store,business_date,input_files,raw_rows,duplicates_removed,final_rows,bytes,sha256")
    for r in manifest:
        print(",".join(map(str,r)))

if __name__=="__main__":
    main()
