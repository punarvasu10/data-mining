import pandas as pd
import glob, os, re, time, sqlite3
import numpy as np
from datasketch import MinHash

BASE = r"C:\Users\ub02-glab-042\Desktop\Punarvasu_T_B\data_2\data_2"

# ----- load -----
files = sorted(glob.glob(os.path.join(BASE, "notices", "*.csv")))
notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
notices["body"] = notices["body"].astype(str)
print("[load]", len(notices))

NAME_RE = re.compile(r"name of work\s*[:\-]\s*(.+)", re.IGNORECASE)
PREFIX_RE = re.compile(r"^(nit for|e-?tender\s*[-\u2013]\s*|corrigendum\s*[-\u2013]\s*|tender notice\s*[-:]\s*)+", re.IGNORECASE)

def normalize(s):
    s = s.lower()
    s = re.sub(r"\d", "#", s)
    s = re.sub(r"[^a-z#\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def extract_signal(body):
    m = NAME_RE.search(body)
    if not m:
        return ""
    return normalize(PREFIX_RE.sub("", m.group(1)))

notices["signal"] = notices["body"].map(extract_signal)

# ----- minhash -----
NUM_PERM = 128
BANDS, ROWS = 32, 4

def shingles(text, k=3):
    w = text.split()
    return set(tuple(w[i:i+k]) for i in range(len(w)-k+1)) if len(w) >= k else set()

sigs = np.zeros((len(notices), NUM_PERM), dtype=np.uint64)
for i, s in enumerate(notices["signal"]):
    m = MinHash(num_perm=NUM_PERM)
    for sh in shingles(s):
        m.update((" ".join(sh)).encode("utf8"))
    sigs[i] = m.hashvalues

# ----- write to SQLite -----
DB = os.path.join(BASE, "notices.db")
if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB)
cur = con.cursor()

cur.execute("""
CREATE TABLE notices (
    notice_id TEXT PRIMARY KEY,
    portal_id TEXT,
    signal TEXT,
    estimated_value INTEGER,
    closing_date TEXT,
    signature BLOB
)""")

cur.execute("""
CREATE TABLE lsh_bands (
    band_id INTEGER,
    band_hash INTEGER,
    notice_id TEXT,
    PRIMARY KEY (band_hash, notice_id)
)""")
cur.execute("CREATE INDEX idx_band_hash ON lsh_bands(band_hash)")

print("[db] inserting...")
t0 = time.time()
for i, row in notices.iterrows():
    cur.execute("INSERT INTO notices VALUES (?,?,?,?,?,?)",
                (row["notice_id"], row["portal_id"], row["signal"],
                 int(row["estimated_value"]), row["closing_date"],
                 sigs[i].tobytes()))
    for b in range(BANDS):
        h = hash(tuple(sigs[i][b*ROWS:(b+1)*ROWS].tolist())) & 0xFFFFFFFFFFFF
        cur.execute("INSERT INTO lsh_bands VALUES (?,?,?)", (b, h, row["notice_id"]))
con.commit()
print("[db] inserted", len(notices), "notices in", round(time.time()-t0,1), "s")
print("[db] file size:", round(os.path.getsize(DB)/1e6, 2), "MB")

# ----- measure candidate list sizes (query band 0 by exact hash) -----
print("")
print("[cand] measuring candidate list size per notice (band 0)...")
t0 = time.time()
sizes = []
for i, row in notices.iterrows():
    h = hash(tuple(sigs[i][0:ROWS].tolist())) & 0xFFFFFFFFFFFF
    cur.execute("SELECT COUNT(*) FROM lsh_bands WHERE band_id=0 AND band_hash=?", (h,))
    sizes.append(cur.fetchone()[0])
sizes = np.array(sizes)
print("[cand] done in", round(time.time()-t0,1), "s")

print("  min:", int(sizes.min()))
print("  median:", int(np.median(sizes)))
print("  p95:", int(np.percentile(sizes, 95)))
print("  p99:", int(np.percentile(sizes, 99)))
print("  max:", int(sizes.max()))
top_pct = float(100.0 * np.sort(sizes)[-120:].sum() / sizes.sum())
print("  top 1% of notices contribute " + str(round(top_pct, 1)) + "% of candidate pairs")

# ----- query plan -----
print("")
print("[plan] EXPLAIN QUERY PLAN for the band lookup")
cur.execute("EXPLAIN QUERY PLAN SELECT notice_id FROM lsh_bands WHERE band_id=0 AND band_hash=12345")
for row in cur.fetchall():
    print(" ", row)

# ----- time one band lookup -----
print("")
print("[time] 1000 band-0 lookups...")
t0 = time.time()
for i in range(1000):
    h = hash(tuple(sigs[i][0:ROWS].tolist())) & 0xFFFFFFFFFFFF
    cur.execute("SELECT notice_id FROM lsh_bands WHERE band_id=0 AND band_hash=?", (h,))
    cur.fetchall()
print("[time]", round(time.time()-t0, 3), "s for 1000 lookups")

con.close()
print("")
print("[done]")