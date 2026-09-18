import pandas as pd
import glob, os, re
import numpy as np

BASE = r"C:\Users\ub02-glab-042\Desktop\Punarvasu_T_B\data_2\data_2"
files = sorted(glob.glob(os.path.join(BASE, 'notices', '*.csv')))
notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
notices['body'] = notices['body'].astype(str)
notices = notices.set_index('notice_id')
labels = pd.read_csv(os.path.join(BASE, 'labelled_pairs.csv'))

# --- Reuse the normalizer from step4 ---
def strip_boilerplate(text):
    lines = text.split("\n")
    out, skip = [], False
    for ln in lines:
        low = ln.lower()
        if "national procurement aggregation service" in low:
            skip = True
        if "state procurement cell" in low:
            skip = True
        if ln.strip().lower().startswith("name of work:"):
            skip = False
        if not skip:
            out.append(ln)
    return "\n".join(out)

def normalize(text):
    text = strip_boilerplate(text)
    text = text.lower()
    text = re.sub(r"\d", "#", text)
    text = re.sub(r"[^a-z#\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def shingles(text, k=3):
    words = text.split()
    return set(tuple(words[i:i+k]) for i in range(len(words)-k+1))

def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0

# --- Compute for all pairs ---
ids_needed = set(labels['notice_id_a']) | set(labels['notice_id_b'])
shingle_sets = {nid: shingles(normalize(notices.loc[nid, 'body']))
                for nid in ids_needed if nid in notices.index}

labels['jaccard'] = [
    jaccard(shingle_sets[a], shingle_sets[b])
    if (a in shingle_sets and b in shingle_sets) else np.nan
    for a, b in zip(labels['notice_id_a'], labels['notice_id_b'])
]

# --- Same pairs below 0.6 ---
bad_same = labels[(labels['label'] == 'same') & (labels['jaccard'] < 0.6)].sort_values('jaccard')
print("=" * 80)
print(f"HARD SAME PAIRS  (n={len(bad_same)})  -- these MUST be merged but score low")
print("=" * 80)
for _, r in bad_same.head(4).iterrows():
    a, b = r['notice_id_a'], r['notice_id_b']
    print(f"\n>>> {a} ({notices.loc[a,'portal_id']}) vs {b} ({notices.loc[b,'portal_id']})  jac={r['jaccard']:.3f}")
    print(f"  A title: {notices.loc[a,'title'][:100]}")
    print(f"  B title: {notices.loc[b,'title'][:100]}")
    # Show what the shingle overlap actually is
    inter = shingle_sets[a] & shingle_sets[b]
    union = shingle_sets[a] | shingle_sets[b]
    print(f"  |A|={len(shingle_sets[a])}  |B|={len(shingle_sets[b])}  |A∩B|={len(inter)}  |A∪B|={len(union)}")
    # Print a few common shingles
    sample = list(inter)[:5]
    print(f"  Sample common shingles: {[' '.join(s) for s in sample]}")
    # Print a few shingles only in A
    only_a = list(shingle_sets[a] - shingle_sets[b])[:5]
    print(f"  Sample A-only shingles: {[' '.join(s) for s in only_a]}")

# --- Different pairs above 0.5 ---
bad_diff = labels[(labels['label'] == 'different') & (labels['jaccard'] >= 0.5)].sort_values('jaccard', ascending=False)
print("\n\n")
print("=" * 80)
print(f"HARD DIFFERENT PAIRS  (n={len(bad_diff)})  -- these MUST stay split but score high")
print("=" * 80)
for _, r in bad_diff.head(4).iterrows():
    a, b = r['notice_id_a'], r['notice_id_b']
    print(f"\n>>> {a} ({notices.loc[a,'portal_id']}) vs {b} ({notices.loc[b,'portal_id']})  jac={r['jaccard']:.3f}")
    print(f"  A title: {notices.loc[a,'title'][:100]}")
    print(f"  B title: {notices.loc[b,'title'][:100]}")
    inter = shingle_sets[a] & shingle_sets[b]
    sample = list(inter)[:5]
    print(f"  Sample common shingles: {[' '.join(s) for s in sample]}")
    