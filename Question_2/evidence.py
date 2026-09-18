import pandas as pd
import glob, os, re, time, sqlite3, hashlib
import numpy as np
from datasketch import MinHash

BASE = r"C:\Users\ub02-glab-042\Desktop\Punarvasu_T_B\data_2\data_2\Question_2"
files = sorted(glob.glob(os.path.join(BASE, "notices", "*.csv")))
notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
notices["body"] = notices["body"].astype(str)
notices = notices.set_index("notice_id")

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

def shingles(text, k=3):
    w = text.split()
    return set(tuple(w[i:i+k]) for i in range(len(w)-k+1)) if len(w) >= k else set()

def jaccard(a, b):
    return len(a & b) / len(a | b) if a or b else 0.0

notices["signal"] = notices["body"].map(extract_signal)
labels = pd.read_csv(os.path.join(BASE, "labelled_pairs.csv"))

print("=" * 78)
print("(a) SIGNAL DEFINITION  --  how the score separates same vs different pairs")
print("=" * 78)

def choice_full(body):
    lines = body.split("\n"); out = []; skip = False
    for ln in lines:
        low = ln.lower()
        if "national procurement aggregation service" in low: skip = True
        if "state procurement cell" in low: skip = True
        if ln.strip().lower().startswith("name of work:"): skip = False
        if not skip: out.append(ln)
    return normalize("\n".join(out))

same_pairs = labels[labels["label"] == "same"].head(2)
diff_pairs = labels[labels["label"] == "different"].head(2)

print("\nTwo same pairs and two different pairs, scored under two signals:\n")
print("  columns: choice-1 (body minus boilerplate)   choice-2 (Name-of-Work only)")
print("-" * 78)
for kind, group in [("same", same_pairs), ("different", diff_pairs)]:
    for _, r in group.iterrows():
        a, b = r["notice_id_a"], r["notice_id_b"]
        s1 = shingles(choice_full(notices.loc[a, "body"]))
        s2 = shingles(choice_full(notices.loc[b, "body"]))
        j1 = jaccard(s1, s2)
        t1 = shingles(extract_signal(notices.loc[a, "body"]))
        t2 = shingles(extract_signal(notices.loc[b, "body"]))
        j2 = jaccard(t1, t2)
        print(f"  {kind:9s}  {a} vs {b}     J_full={j1:.3f}     J_nameofwork={j2:.3f}")

print("\nDistributions over all 900 labelled pairs, under each choice:")
print("-" * 78)
for choice_name, choice_fn in [("body - boilerplate", choice_full),
                               ("Name-of-Work only", extract_signal)]:
    jac_same = []; jac_diff = []
    for _, r in labels.iterrows():
        a, b, y = r["notice_id_a"], r["notice_id_b"], r["label"]
        sa = shingles(choice_fn(notices.loc[a, "body"]))
        sb = shingles(choice_fn(notices.loc[b, "body"]))
        j = jaccard(sa, sb)
        (jac_same if y == "same" else jac_diff).append(j)
    print(f"  {choice_name:22s}  same: mean={np.mean(jac_same):.3f} min={np.min(jac_same):.3f} "
          f"|  different: mean={np.mean(jac_diff):.3f} max={np.max(jac_diff):.3f}")

print("\n" + "=" * 78)
print("(b) MINHASH SIZE  --  measured error vs exact Jaccard on 900 labelled pairs")
print("=" * 78)

target_err = 0.05; p = 0.8
k_needed = int(np.ceil(p * (1-p) / (target_err**2)))
print(f"\n  Application target: error <= {target_err} at p={p}")
print(f"  Formula sqrt(p(1-p)/k) <= err  =>  k >= {k_needed}")
print(f"  We adopt k = 128 (2x headroom).")

NUM_PERM = 128
sigs = {}
for nid in set(labels["notice_id_a"]) | set(labels["notice_id_b"]):
    m = MinHash(num_perm=NUM_PERM)
    for sh in shingles(extract_signal(notices.loc[nid, "body"])):
        m.update((" ".join(sh)).encode("utf8"))
    sigs[nid] = np.array(m.hashvalues, dtype=np.uint64)

errs = []
for _, r in labels.iterrows():
    a, b = r["notice_id_a"], r["notice_id_b"]
    exact = jaccard(shingles(extract_signal(notices.loc[a, "body"])),
                    shingles(extract_signal(notices.loc[b, "body"])))
    est = float(np.mean(sigs[a] == sigs[b]))
    errs.append(abs(exact - est))
errs = np.array(errs)
print(f"\n  Realised error over n={len(errs)} pairs:")
print(f"    mean  = {errs.mean():.4f}")
print(f"    p50   = {np.percentile(errs,50):.4f}")
print(f"    p95   = {np.percentile(errs,95):.4f}")
print(f"    p99   = {np.percentile(errs,99):.4f}")
print(f"    max   = {errs.max():.4f}")

print("\n" + "=" * 78)
print("(c) LSH 32 x 4  --  P(retrieved | true similarity) and operating point")
print("=" * 78)
B, R = 32, 4
def p_retrieve(s, b=B, r=R):
    return 1 - (1 - s**r)**b
print(f"\n  Curve for b={B} bands x r={R} rows = {B*R} perms:")
print(f"    {'s':>5s}   {'P(retrieve|s)':>15s}")
for s in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]:
    print(f"    {s:>5.2f}   {p_retrieve(s):>15.4f}")
print("\n  Operating point: threshold 0.8 (cost asymmetry C_merge/C_split = 100:1)")

print("\n" + "=" * 78)
print("(d) DB access path  --  B-tree index vs full scan")
print("=" * 78)

sigs_full = np.zeros((len(notices), NUM_PERM), dtype=np.uint64)
for i, s in enumerate(notices["signal"]):
    m = MinHash(num_perm=NUM_PERM)
    for sh in shingles(s):
        m.update((" ".join(sh)).encode("utf8"))
    sigs_full[i] = m.hashvalues

def band_hash(sig, b):
    return hash(tuple(sig[b*R:(b+1)*R].tolist())) & 0xFFFFFFFFFFFF

for use_index in [True, False]:
    DB = os.path.join(BASE, "ev_" + ("idx" if use_index else "noidx") + ".db")
    if os.path.exists(DB): os.remove(DB)
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("CREATE TABLE lsh_bands (band_id INTEGER, band_hash INTEGER, notice_id TEXT)")
    if use_index:
        cur.execute("CREATE INDEX idx_band_hash ON lsh_bands(band_hash)")
    for i in range(len(notices)):
        for b in range(B):
            cur.execute("INSERT INTO lsh_bands VALUES (?,?,?)",
                        (b, band_hash(sigs_full[i], b), notices.index[i]))
    con.commit()
    cur.execute("EXPLAIN QUERY PLAN SELECT notice_id FROM lsh_bands WHERE band_id=0 AND band_hash=12345")
    plan = cur.fetchall()
    t0 = time.time()
    for i in range(1000):
        cur.execute("SELECT notice_id FROM lsh_bands WHERE band_id=0 AND band_hash=?",
                    (band_hash(sigs_full[i], 0),))
        cur.fetchall()
    dt = time.time() - t0
    print(f"  use_index={use_index}  plan={plan}  time(1000 lookups)={dt:.3f}s")
    con.close()

print("\n" + "=" * 78)
print("(e) Uneven work across the corpus + measured mitigation cost")
print("=" * 78)
bucket_map = {}
for i in range(len(notices)):
    for b in range(B):
        key = (b, band_hash(sigs_full[i], b))
        bucket_map.setdefault(key, []).append(i)
candidates = []
for i in range(len(notices)):
    seen = {}
    for b in range(B):
        key = (b, band_hash(sigs_full[i], b))
        for j in bucket_map.get(key, []):
            if j == i or j in seen: continue
            seen[j] = float(np.mean(sigs_full[i] == sigs_full[j]))
    candidates.append(sorted(seen.items(), key=lambda kv: -kv[1]))
sizes = np.array([len(c) for c in candidates])
print(f"\n  Candidate list sizes:")
print(f"    min={sizes.min()}  median={int(np.median(sizes))}  "
      f"p95={int(np.percentile(sizes,95))}  p99={int(np.percentile(sizes,99))}  max={sizes.max()}")
top1 = float(100.0 * np.sort(sizes)[-120:].sum() / sizes.sum())
print(f"    top 1% contribute {top1:.1f}% of all candidate pairs")
print(f"    total candidate pairs: {int(sizes.sum())}")

idx_map = {nid: i for i, nid in enumerate(notices.index)}
def retrieved(a, b, cap):
    ia, ib = idx_map[a], idx_map[b]
    if cap is None:
        return ia in [x[0] for x in candidates[ib]] or ib in [x[0] for x in candidates[ia]]
    return (any(x[0] == ia for x in candidates[ib][:cap])
            or any(x[0] == ib for x in candidates[ia][:cap]))

print(f"\n  Mitigation: cap candidate list at C")
print(f"    {'C':>5s}  {'pairs':>10s}  {'recall(same)':>12s}  {'fp_rate(diff)':>13s}")
for cap in [None, 100, 30, 10, 5]:
    sh = st = dh = dtt = 0
    for _, r in labels.iterrows():
        a, b, y = r["notice_id_a"], r["notice_id_b"], r["label"]
        if a not in idx_map or b not in idx_map: continue
        if y == "same":
            st += 1; sh += retrieved(a, b, cap)
        else:
            dtt += 1; dh += retrieved(a, b, cap)
    total = sum(min(cap, len(c)) if cap else len(c) for c in candidates)
    tag = "none" if cap is None else str(cap)
    print(f"    {tag:>5s}  {total:>10d}  {sh/st:>12.3f}  {dh/dtt:>13.3f}")

notices["card_id"] = notices["signal"].map(lambda s: hashlib.sha1(s.encode("utf8")).hexdigest()[:12])
print(f"\n  Stable card IDs: unique={notices['card_id'].nunique()} of {len(notices)}  "
      f"avg copies={len(notices)/notices['card_id'].nunique():.2f}")
print("\n[done]")