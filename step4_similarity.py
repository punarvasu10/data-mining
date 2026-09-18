import pandas as pd
import glob, os, re
from collections import Counter
import numpy as np

BASE = r"C:\Users\ub02-glab-042\Desktop\Punarvasu_T_B\data_2\data_2"
files = sorted(glob.glob(os.path.join(BASE, 'notices', '*.csv')))
notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
notices['body'] = notices['body'].astype(str)
notices = notices.set_index('notice_id')
labels = pd.read_csv(os.path.join(BASE, 'labelled_pairs.csv'))

# ---------- Normalization pipeline ----------
# 1. Lowercase
# 2. Remove punctuation except spaces and digits
# 3. Collapse whitespace
# 4. Strip the boilerplate blocks
NPAS_MARK = "NATIONAL PROCUREMENT AGGREGATION SERVICE"
SPC_MARK  = "STATE PROCUREMENT CELL"

def strip_boilerplate(text):
    # Remove NPAS block: everything from "GOVERNMENT OF INDIA -- NATIONAL..." up to the last occurrence
    # Easiest robust approach: drop any line that is part of the boilerplate
    lines = text.split("\n")
    out = []
    skip = False
    for ln in lines:
        low = ln.lower()
        # crude block detection
        if "national procurement aggregation service" in low:
            skip = True
        if "state procurement cell" in low:
            skip = True
        # stop skipping when we hit the structured data section
        if ln.strip().lower().startswith("name of work:"):
            skip = False
        if not skip:
            out.append(ln)
    return "\n".join(out)

def normalize(text):
    text = strip_boilerplate(text)
    text = text.lower()
    # replace digits with '#'
    text = re.sub(r"\d", "#", text)
    # remove punctuation
    text = re.sub(r"[^a-z#\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def shingles(text, k=3):
    """k word shingles"""
    words = text.split()
    return set(tuple(words[i:i+k]) for i in range(len(words)-k+1))

def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

# ---------- Test on labelled pairs ----------
print("Building shingle sets for label pairs (this may take a moment)...")
ids_needed = set(labels['notice_id_a']) | set(labels['notice_id_b'])
shingle_sets = {}
for nid in ids_needed:
    if nid in notices.index:
        norm = normalize(notices.loc[nid, 'body'])
        shingle_sets[nid] = shingles(norm, k=3)

# Compute Jaccard for every labelled pair, split by label
rows = []
for _, r in labels.iterrows():
    a, b, y = r['notice_id_a'], r['notice_id_b'], r['label']
    if a in shingle_sets and b in shingle_sets:
        s = jaccard(shingle_sets[a], shingle_sets[b])
        rows.append((a, b, y, s))

df = pd.DataFrame(rows, columns=['a','b','label','jaccard'])
print(f"\nScored {len(df)} pairs")

print("\n" + "=" * 60)
print("JACCARD DISTRIBUTION BY LABEL")
print("=" * 60)
print(df.groupby('label')['jaccard'].describe())

# Histogram-ish
print("\n" + "=" * 60)
print("Histogram of Jaccard by label")
print("=" * 60)
bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.001]
for lab in ['same', 'different']:
    sub = df[df['label'] == lab]
    h, _ = np.histogram(sub['jaccard'], bins=bins)
    print(f"\n{lab} (n={len(sub)}):")
    for i in range(len(h)):
        print(f"  [{bins[i]:.2f}, {bins[i+1]:.2f})  {h[i]:5d}  {'#' * int(h[i]/max(1,len(sub))*50)}")

# Where would a threshold sit?
print("\n" + "=" * 60)
print("Threshold tradeoff")
print("=" * 60)
for t in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9]:
    same_hit = ((df['label']=='same') & (df['jaccard'] >= t)).sum()
    same_tot = (df['label']=='same').sum()
    diff_hit = ((df['label']=='different') & (df['jaccard'] >= t)).sum()
    diff_tot = (df['label']=='different').sum()
    recall = same_hit / same_tot if same_tot else 0
    fp_rate = diff_hit / diff_tot if diff_tot else 0
    print(f"  t={t:.2f}  recall(same)={recall:.3f}  fp_rate(diff)={fp_rate:.3f}  "
          f"merges={same_hit+diff_hit}")