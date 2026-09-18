import pandas as pd
import glob, os, re, time, pickle
import numpy as np

BASE = r"C:\Users\ub02-glab-042\Desktop\Punarvasu_T_B\data_2\data_2"

# ============================================================
# STEP 1: LOAD
# ============================================================
print("[load] reading notices...")
files = sorted(glob.glob(os.path.join(BASE, "notices", "*.csv")))
notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
notices["body"]  = notices["body"].astype(str)
notices["title"] = notices["title"].astype(str)
print(f"[load] {len(notices)} notices from {len(files)} files")

# ============================================================
# STEP 2: EXTRACT SIGNAL  (name-of-work line)
# ============================================================
NAME_RE = re.compile(r"name of work\s*[:\-]\s*(.+)", re.IGNORECASE)
PREFIX_RE = re.compile(
    r"^(nit for|e-?tender\s*[-\u2013]\s*|corrigendum\s*[-\u2013]\s*|tender notice\s*[-:]\s*)+",
    re.IGNORECASE,
)

def normalize(s):
    s = s.lower()
    s = re.sub(r"\d", "#", s)
    s = re.sub(r"[^a-z#\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def extract_signal(body):
    """Return the normalized Name-of-Work value, empty string if not found."""
    m = NAME_RE.search(body)
    if not m:
        # try first non-empty line as fallback
        for ln in body.split("\n"):
            ln = ln.strip()
            if ln:
                return normalize(ln[:300])
        return ""
    val = m.group(1)
    val = PREFIX_RE.sub("", val)
    return normalize(val)

print("[signal] extracting Name-of-Work from every notice...")
t0 = time.time()
notices["signal"] = notices["body"].map(extract_signal)
notices["signal_len"] = notices["signal"].str.len()
print(f"[signal] done in {time.time()-t0:.1f}s")
print(notices["signal_len"].describe())

# ============================================================
# STEP 3: SHINGLES + MINHASH
# ============================================================
def shingles(text, k=3):
    w = text.split()
    if len(w) < k:
        return set()
    return set(tuple(w[i:i+k]) for i in range(len(w) - k + 1))

print("[shingle] building shingle sets...")
t0 = time.time()
shingle_sets = [shingles(s) for s in notices["signal"]]
print(f"[shingle] done in {time.time()-t0:.1f}s")
print(f"[shingle] avg shingles per notice: {np.mean([len(s) for s in shingle_sets]):.1f}")

# MinHash with 128 permutations — DERIVED size (we will justify later)
from datasketch import MinHash
NUM_PERM = 128

print(f"[minhash] computing {NUM_PERM}-perm signatures...")
t0 = time.time()
sigs = []
for s in shingle_sets:
    m = MinHash(num_perm=NUM_PERM)
    for sh in s:
        m.update((" ".join(sh)).encode("utf8"))
    sigs.append(np.array(m.hashvalues, dtype=np.uint64))
print(f"[minhash] done in {time.time()-t0:.1f}s")

# ============================================================
# STEP 4: LSH  (bands of rows)
# ============================================================
from datasketch import MinHashLSH

# b*r = NUM_PERM ; pick b=32, r=4  → high recall, manageable candidate lists
BANDS, ROWS = 32, 4
assert BANDS * ROWS == NUM_PERM

print(f"[lsh] inserting into LSH ({BANDS} bands x {ROWS} rows)...")
t0 = time.time()
lsh = MinHashLSH(threshold=0.7, num_perm=NUM_PERM)
for i, sig in enumerate(sigs):
    m = MinHash(num_perm=NUM_PERM)
    m.hashvalues = sig
    lsh.insert(f"N{i:06d}", m)
print(f"[lsh] done in {time.time()-t0:.1f}s")

# ============================================================
# STEP 5: CANDIDATE RETRIEVAL + CLASSIFY ON LABELS
# ============================================================
print("\n[eval] running candidate retrieval on labelled pairs...")

# Map original notice_id → row index in 'notices'
id_to_idx = {nid: i for i, nid in enumerate(notices["notice_id"])}

labels = pd.read_csv(os.path.join(BASE, "labelled_pairs.csv"))

def jaccard_sig(a, b):
    return float(np.mean(a == b))

# For each label pair, compute MinHash-estimated Jaccard
rows = []
for _, r in labels.iterrows():
    a, b, y = r["notice_id_a"], r["notice_id_b"], r["label"]
    if a not in id_to_idx or b not in id_to_idx:
        continue
    ia, ib = id_to_idx[a], id_to_idx[b]
    est = jaccard_sig(sigs[ia], sigs[ib])
    rows.append((y, est))

df = pd.DataFrame(rows, columns=["label", "jaccard_mh"])
print(df.groupby("label")["jaccard_mh"].describe().round(3))

print("\n[eval] threshold tradeoff (MinHash estimate):")
for t in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    sh = ((df["label"]=="same") & (df["jaccard_mh"] >= t)).sum()
    st = (df["label"]=="same").sum()
    dh = ((df["label"]=="different") & (df["jaccard_mh"] >= t)).sum()
    dt = (df["label"]=="different").sum()
    print(f"  t={t:.2f}  recall={sh/st:.3f}  fp_rate={dh/dt:.3f}  merges={sh+dh}")

# ============================================================
# STEP 6: MEASURE ESTIMATION ERROR
# ============================================================
print("\n[error] exact Jaccard vs MinHash estimate on labels...")
errs = []
for _, r in labels.iterrows():
    a, b = r["notice_id_a"], r["notice_id_b"]
    if a not in id_to_idx or b not in id_to_idx:
        continue
    ia, ib = id_to_idx[a], id_to_idx[b]
    exact = len(shingle_sets[ia] & shingle_sets[ib]) / max(1, len(shingle_sets[ia] | shingle_sets[ib]))
    est   = jaccard_sig(sigs[ia], sigs[ib])
    errs.append(abs(exact - est))

errs = np.array(errs)
print(f"  n={len(errs)}")
print(f"  mean abs err: {errs.mean():.4f}")
print(f"  p50: {np.percentile(errs,50):.4f}")
print(f"  p95: {np.percentile(errs,95):.4f}")
print(f"  p99: {np.percentile(errs,99):.4f}")
print(f"  max: {errs.max():.4f}")

print("\n[done]")




# ---------- EVAL ON LABELS ----------
print("")
print("[eval] evaluating on labelled pairs...")
id_to_idx = {nid: i for i, nid in enumerate(notices["notice_id"])}
labels = pd.read_csv(os.path.join(BASE, "labelled_pairs.csv"))

def jac_sig(a, b):
    return float(np.mean(a == b))

rows = []
for _, r in labels.iterrows():
    a, b, y = r["notice_id_a"], r["notice_id_b"], r["label"]
    if a not in id_to_idx or b not in id_to_idx:
        continue
    est = jac_sig(sigs[id_to_idx[a]], sigs[id_to_idx[b]])
    rows.append((y, est))

df = pd.DataFrame(rows, columns=["label", "jaccard_mh"])
print(df.groupby("label")["jaccard_mh"].describe().round(3))

print("")
print("[eval] threshold tradeoff")
for t in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    sh = ((df["label"]=="same") & (df["jaccard_mh"] >= t)).sum()
    st = (df["label"]=="same").sum()
    dh = ((df["label"]=="different") & (df["jaccard_mh"] >= t)).sum()
    dt = (df["label"]=="different").sum()
    print("  t=%.2f  recall=%.3f  fp_rate=%.3f  merges=%d" % (t, sh/st, dh/dt, sh+dh))

# ---------- ERROR ----------
errs = []
for _, r in labels.iterrows():
    a, b = r["notice_id_a"], r["notice_id_b"]
    if a not in id_to_idx or b not in id_to_idx:
        continue
    ia, ib = id_to_idx[a], id_to_idx[b]
    exact = len(shingle_sets[ia] & shingle_sets[ib]) / max(1, len(shingle_sets[ia] | shingle_sets[ib]))
    est = jac_sig(sigs[ia], sigs[ib])
    errs.append(abs(exact - est))

errs = np.array(errs)
print("")
print("[error]")
print("  n=", len(errs))
print("  mean abs err: %.4f" % errs.mean())
print("  p95: %.4f" % np.percentile(errs,95))
print("  p99: %.4f" % np.percentile(errs,99))
print("  max: %.4f" % errs.max())
print("[done]")
