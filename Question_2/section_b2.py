import pandas as pd
import glob, os, re, time, sqlite3, hashlib
import numpy as np
from datasketch import MinHash

BASE = r"C:\Users\ub02-glab-042\Desktop\Punarvasu_T_B\data_2\data_2"

# ============================================================
# LOAD + SIGNAL
# ============================================================
files = sorted(glob.glob(os.path.join(BASE, "notices", "*.csv")))
notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
notices["body"] = notices["body"].astype(str)

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
print("[load]", len(notices))

# ============================================================
# MINHASH + BANDS
# ============================================================
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

def band_hash(sig, b):
    return hash(tuple(sig[b*ROWS:(b+1)*ROWS].tolist())) & 0xFFFFFFFFFFFF

# ============================================================
# (d) PLANNER: WITH INDEX vs WITHOUT INDEX
# ============================================================
DB = os.path.join(BASE, "notices.db")
if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB)
cur = con.cursor()
cur.execute("CREATE TABLE lsh_bands (band_id INTEGER, band_hash INTEGER, notice_id TEXT)")
cur.execute("CREATE INDEX idx_band_hash ON lsh_bands(band_hash)")

# insert
for i, row in notices.iterrows():
    for b in range(BANDS):
        cur.execute("INSERT INTO lsh_bands VALUES (?,?,?)",
                    (b, band_hash(sigs[i], b), row["notice_id"]))
con.commit()

print("")
print("[plan-with-index]")
cur.execute("EXPLAIN QUERY PLAN SELECT notice_id FROM lsh_bands WHERE band_id=0 AND band_hash=12345")
for r in cur.fetchall():
    print(" ", r)

print("[time-with-index] 1000 lookups:")
t0 = time.time()
for i in range(1000):
    cur.execute("SELECT notice_id FROM lsh_bands WHERE band_id=0 AND band_hash=?",
                (band_hash(sigs[i], 0),))
    cur.fetchall()
print(" ", round(time.time()-t0, 3), "s")

# force full scan by disabling index
print("")
print("[plan-forced-full-scan] (INDEXED BY not used -> sqlite has no way to hint, so we drop index)")
cur.execute("DROP INDEX idx_band_hash")
con.commit()
cur.execute("EXPLAIN QUERY PLAN SELECT notice_id FROM lsh_bands WHERE band_id=0 AND band_hash=12345")
for r in cur.fetchall():
    print(" ", r)

print("[time-full-scan] 1000 lookups:")
t0 = time.time()
for i in range(1000):
    cur.execute("SELECT notice_id FROM lsh_bands WHERE band_id=0 AND band_hash=?",
                (band_hash(sigs[i], 0),))
    cur.fetchall()
print(" ", round(time.time()-t0, 3), "s")

# restore index
cur.execute("CREATE INDEX idx_band_hash ON lsh_bands(band_hash)")
con.commit()

# ============================================================
# (e) DISTRIBUTION OF WORK
# ============================================================
print("")
print("[dist] candidate list sizes across all 32 bands (union per notice)")
t0 = time.time()
sizes_all = []
for i in range(len(notices)):
    ids = set()
    for b in range(BANDS):
        cur.execute("SELECT notice_id FROM lsh_bands WHERE band_id=? AND band_hash=?",
                    (b, band_hash(sigs[i], b)))
        for row in cur.fetchall():
            ids.add(row[0])
    sizes_all.append(len(ids))
sizes_all = np.array(sizes_all)
print("[dist] done in", round(time.time()-t0, 1), "s")
print("  min:", int(sizes_all.min()))
print("  median:", int(np.median(sizes_all)))
print("  p95:", int(np.percentile(sizes_all, 95)))
print("  p99:", int(np.percentile(sizes_all, 99)))
print("  max:", int(sizes_all.max()))
top = float(100.0 * np.sort(sizes_all)[-120:].sum() / sizes_all.sum())
print("  top 1% contribute " + str(round(top, 1)) + "% of candidate pairs")

# ============================================================
# (e) MITIGATION: cap candidate list at C, re-measure
# ============================================================
print("")
print("[mitigation] capping candidate list at 30 per notice")
sizes_capped = np.minimum(sizes_all, 30)
total_before = int(sizes_all.sum())
total_after = int(sizes_capped.sum())
print("  total candidate pairs before:", total_before)
print("  total candidate pairs after :", total_after)
print("  reduction: " + str(round(100*(1 - total_after/total_before), 1)) + "%")

# ============================================================
# RETRIEVAL QUALITY COST on labelled pairs
# ============================================================
print("")
print("[quality] recall on labelled pairs under cap")
labels = pd.read_csv(os.path.join(BASE, "labelled_pairs.csv"))
id_to_idx = {nid: i for i, nid in enumerate(notices["notice_id"])}

def exact_jac(a, b):
    A = shingles(notices.loc[id_to_idx[a], "signal"])
    B = shingles(notices.loc[id_to_idx[b], "signal"])
    return len(A & B) / max(1, len(A | B))

def retrieved(a, b, cap):
    """Did the pair survive candidate retrieval? cap=None means no cap."""
    ia, ib = id_to_idx[a], id_to_idx[b]
    common_bands = 0
    for b_idx in range(BANDS):
        if band_hash(sigs[ia], b_idx) == band_hash(sigs[ib], b_idx):
            common_bands += 1
    if common_bands == 0:
        return False
    if cap is None:
        return True
    return min(sizes_all[ia], cap) > 0 and min(sizes_all[ib], cap) > 0

for cap in [None, 100, 30, 10]:
    same_ok = 0
    same_tot = 0
    diff_ok = 0
    diff_tot = 0
    for _, r in labels.iterrows():
        a, b, y = r["notice_id_a"], r["notice_id_b"], r["label"]
        if a not in id_to_idx or b not in id_to_idx:
            continue
        if y == "same":
            same_tot += 1
            if retrieved(a, b, cap):
                same_ok += 1
        else:
            diff_tot += 1
            if retrieved(a, b, cap):
                diff_ok += 1
    label = "no cap" if cap is None else "cap=" + str(cap)
    print("  " + label + ": recall(same)=" + str(round(same_ok/same_tot,3))
          + "  fp_rate(diff)=" + str(round(diff_ok/diff_tot,3)))

# ============================================================
# STABLE CARD IDs
# ============================================================
print("")
print("[stable-id] content-hash based card IDs")
def content_hash(signal):
    return hashlib.sha1(signal.encode("utf8")).hexdigest()[:12]

notices["card_id"] = notices["signal"].map(content_hash)
n_unique = notices["card_id"].nunique()
n_total = len(notices)
print("  unique card IDs:", n_unique, "of", n_total, "notices")
print("  merge factor (duplicates per card):", round(n_total / n_unique, 2))

con.close()
print("")
print("[done]")