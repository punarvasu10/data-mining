import pandas as pd
import glob, os, re, time, sqlite3
import numpy as np
from datasketch import MinHash

BASE = r"C:\Users\ub02-glab-042\Desktop\Punarvasu_T_B\data_2\data_2"
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
    return normalize(PREFIX_RE.sub("", m.group(1))) if m else ""

notices["signal"] = notices["body"].map(extract_signal)

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

print("[d] index vs no-index, clean DBs")
for use_index in [True, False]:
    DB = os.path.join(BASE, "notices_" + ("idx" if use_index else "noidx") + ".db")
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("CREATE TABLE lsh_bands (band_id INTEGER, band_hash INTEGER, notice_id TEXT)")
    if use_index:
        cur.execute("CREATE INDEX idx_band_hash ON lsh_bands(band_hash)")
    for i, row in notices.iterrows():
        for b in range(BANDS):
            cur.execute("INSERT INTO lsh_bands VALUES (?,?,?)",
                        (b, band_hash(sigs[i], b), row["notice_id"]))
    con.commit()
    cur.execute("EXPLAIN QUERY PLAN SELECT notice_id FROM lsh_bands WHERE band_id=0 AND band_hash=12345")
    plan = cur.fetchall()
    t0 = time.time()
    for i in range(1000):
        cur.execute("SELECT notice_id FROM lsh_bands WHERE band_id=0 AND band_hash=?",
                    (band_hash(sigs[i], 0),))
        cur.fetchall()
    dt = time.time() - t0
    print("  use_index=" + str(use_index) + "  plan=" + str(plan) + "  time=" + str(round(dt,3)) + "s")
    con.close()

print("")
print("[e] building in-memory LSH bucket map...")
bucket_map = {}
for i in range(len(notices)):
    for b in range(BANDS):
        key = (b, band_hash(sigs[i], b))
        bucket_map.setdefault(key, []).append(i)

print("[e] computing candidate lists...")
candidates = []
for i in range(len(notices)):
    seen = {}
    for b in range(BANDS):
        key = (b, band_hash(sigs[i], b))
        for j in bucket_map.get(key, []):
            if j == i:
                continue
            if j in seen:
                continue
            seen[j] = float(np.mean(sigs[i] == sigs[j]))
    candidates.append(sorted(seen.items(), key=lambda kv: -kv[1]))

sizes = np.array([len(c) for c in candidates])
print("  min:", int(sizes.min()), " median:", int(np.median(sizes)),
      " p95:", int(np.percentile(sizes,95)), " p99:", int(np.percentile(sizes,99)),
      " max:", int(sizes.max()))
print("  top 1% contribute " + str(round(float(100.0*np.sort(sizes)[-120:].sum()/sizes.sum()),1)) + "% of candidate pairs")

labels = pd.read_csv(os.path.join(BASE, "labelled_pairs.csv"))
id_to_idx = {nid: i for i, nid in enumerate(notices["notice_id"])}

def pair_retrieved(a, b, cap):
    ia, ib = id_to_idx[a], id_to_idx[b]
    if cap is None:
        return ia in [x[0] for x in candidates[ib]] or ib in [x[0] for x in candidates[ia]]
    a_in_b = any(x[0] == ia for x in candidates[ib][:cap])
    b_in_a = any(x[0] == ib for x in candidates[ia][:cap])
    return a_in_b or b_in_a

print("")
print("[e] quality vs cap")
for cap in [None, 100, 30, 10, 5]:
    same_ok = same_tot = diff_ok = diff_tot = 0
    for _, r in labels.iterrows():
        a, b, y = r["notice_id_a"], r["notice_id_b"], r["label"]
        if a not in id_to_idx or b not in id_to_idx:
            continue
        if y == "same":
            same_tot += 1
            same_ok += pair_retrieved(a, b, cap)
        else:
            diff_tot += 1
            diff_ok += pair_retrieved(a, b, cap)
    tag = "no cap" if cap is None else ("cap=" + str(cap))
    print("  " + tag + ": recall(same)=" + str(round(same_ok/same_tot,3))
          + "  fp_rate(diff)=" + str(round(diff_ok/diff_tot,3)))

print("")
print("[e] total candidate pairs")
for cap in [None, 100, 30, 10, 5]:
    tot = sum(min(cap, len(c)) if cap else len(c) for c in candidates)
    print("  " + ("no cap" if cap is None else "cap="+str(cap)) + ": " + str(tot))

print("")
print("[done]")