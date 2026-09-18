import pandas as pd
import glob, os, re
import numpy as np

BASE = r"C:\Users\ub02-glab-042\Desktop\Punarvasu_T_B\data_2\data_2"
files = sorted(glob.glob(os.path.join(BASE, "notices", "*.csv")))
notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
notices["body"] = notices["body"].astype(str)
notices["title"] = notices["title"].astype(str)
notices = notices.set_index("notice_id")
labels = pd.read_csv(os.path.join(BASE, "labelled_pairs.csv"))
print("Loaded", len(notices), "notices,", len(labels), "labels")

def clean_text(s):
    s = s.lower()
    s = re.sub(r"\d", "#", s)
    s = re.sub(r"[^a-z#\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def shingles(text, k=3):
    w = text.split()
    return set(tuple(w[i:i+k]) for i in range(len(w)-k+1))

def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0

PREFIX_PAT = re.compile(r"^(nit for|e-?tender\s*[-\u2013]\s*|corrigendum\s*[-\u2013]\s*|tender notice\s*[-:]\s*)+", re.IGNORECASE)

def clean_title(t):
    t = PREFIX_PAT.sub("", t).strip()
    t = re.sub(r"\[.*?\]", " ", t)
    t = re.sub(r"\(.*?\)", " ", t)
    return clean_text(t)

def name_of_work_line(body):
    for ln in body.split("\n"):
        s = ln.strip()
        if s.lower().startswith("name of work"):
            val = s.split(":", 1)[1] if ":" in s else s
            return clean_text(val)
    return ""

ids_needed = set(labels["notice_id_a"]) | set(labels["notice_id_b"])
print("Building representations...")
sets_A = {nid: shingles(clean_title(notices.loc[nid, "title"])) for nid in ids_needed if nid in notices.index}
sets_B = {nid: shingles(name_of_work_line(notices.loc[nid, "body"])) for nid in ids_needed if nid in notices.index}
sets_C = {nid: shingles(clean_title(notices.loc[nid, "title"]) + " " + name_of_work_line(notices.loc[nid, "body"])) for nid in ids_needed if nid in notices.index}
print("Done:", len(sets_A))

def evaluate(sets, name):
    print("\n" + "=" * 70)
    print("APPROACH:", name)
    print("=" * 70)
    rows = []
    for _, r in labels.iterrows():
        a, b, y = r["notice_id_a"], r["notice_id_b"], r["label"]
        if a in sets and b in sets:
            rows.append((y, jaccard(sets[a], sets[b])))
    df = pd.DataFrame(rows, columns=["label", "jaccard"])
    print(df.groupby("label")["jaccard"].describe().round(3))
    print("\nThreshold tradeoff:")
    for t in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        sh = ((df["label"]=="same") & (df["jaccard"] >= t)).sum()
        st = (df["label"]=="same").sum()
        dh = ((df["label"]=="different") & (df["jaccard"] >= t)).sum()
        dt = (df["label"]=="different").sum()
        print(f"  t={t:.2f}  recall={sh/st:.3f}  fp_rate={dh/dt:.3f}  merges={sh+dh}")

evaluate(sets_A, "A: TITLE ONLY")
evaluate(sets_B, "B: NAME-OF-WORK LINE ONLY")
evaluate(sets_C, "C: TITLE + NAME-OF-WORK")

print("\n" + "=" * 70)
print("CLEANED TITLE SAMPLES")
print("=" * 70)
for nid in list(ids_needed)[:8]:
    if nid in notices.index:
        print(f"  {nid} ({notices.loc[nid,'portal_id']}):")
        print(f"    raw:     {notices.loc[nid,'title'][:100]}")
        print(f"    cleaned: {clean_title(notices.loc[nid,'title'])}")
