import pandas as pd
import glob, os, re
import numpy as np

BASE = r"C:\Users\ub02-glab-042\Desktop\Punarvasu_T_B\data_2\data_2"
files = sorted(glob.glob(os.path.join(BASE, 'notices', '*.csv')))
print(f"Found {len(files)} files")

notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
notices['body'] = notices['body'].astype(str)
notices = notices.set_index('notice_id')
labels = pd.read_csv(os.path.join(BASE, 'labelled_pairs.csv'))
print(f"Notices: {len(notices)}, labels: {len(labels)}")

TEMPLATE_PHRASES = [
    r"the work comprises .*? approved drawings\.?",
    r"the contractor shall execute .*?(?=the contractor|$)",
    r"scope of work",
    r"abstract bill of quantities",
    r"key dates",
]

def strip_boilerplate(text):
    lines = text.split("\n")
    out, skip = [], False
    for ln in lines:
        low = ln.lower()
        if "national procurement aggregation service" in low or "state procurement cell" in low:
            skip = True
        if ln.strip().lower().startswith("name of work:"):
            skip = False
        if not skip:
            out.append(ln)
    return "\n".join(out)

def header_only(text):
    text = strip_boilerplate(text)
    for marker in ["SCOPE OF WORK", "ABSTRACT BILL", "KEY DATES"]:
        idx = text.upper().find(marker)
        if idx != -1:
            text = text[:idx]
    for pat in TEMPLATE_PHRASES:
        text = re.sub(pat, " ", text, flags=re.IGNORECASE | re.DOTALL)
    return text

def normalize(text):
    text = header_only(text)
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

ids_needed = set(labels['notice_id_a']) | set(labels['notice_id_b'])
print("Building shingle sets...")
sets = {}
for nid in ids_needed:
    if nid in notices.index:
        sets[nid] = shingles(normalize(notices.loc[nid, 'body']))
print(f"Built {len(sets)}")

print("\n" + "=" * 80)
print("SAMPLE NORMALIZED HEADER")
print("=" * 80)
sid = list(sets.keys())[0]
print(normalize(notices.loc[sid, 'body'])[:800])

rows = []
for _, r in labels.iterrows():
    a, b, y = r['notice_id_a'], r['notice_id_b'], r['label']
    if a in sets and b in sets:
        rows.append((a, b, y, jaccard(sets[a], sets[b])))

df = pd.DataFrame(rows, columns=['a','b','label','jaccard'])
print("\n" + "=" * 80)
print("JACCARD BY LABEL (HEADER-ONLY)")
print("=" * 80)
print(df.groupby('label')['jaccard'].describe())

bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.001]
for lab in ['same', 'different']:
    sub = df[df['label'] == lab]
    h, _ = np.histogram(sub['jaccard'], bins=bins)
    print(f"\n{lab} (n={len(sub)}):")
    for i in range(len(h)):
        bar = '#' * int(h[i]/max(1,len(sub))*50)
        print(f"  [{bins[i]:.2f}, {bins[i+1]:.2f})  {h[i]:5d}  {bar}")

print("\n" + "=" * 80)
print("THRESHOLD TRADEOFF (HEADER-ONLY)")
print("=" * 80)
for t in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
    same_hit = ((df['label']=='same') & (df['jaccard'] >= t)).sum()
    same_tot = (df['label']=='same').sum()
    diff_hit = ((df['label']=='different') & (df['jaccard'] >= t)).sum()
    diff_tot = (df['label']=='different').sum()
    print(f"  t={t:.2f}  recall={same_hit/same_tot:.3f}  fp_rate={diff_hit/diff_tot:.3f}  merges={same_hit+diff_hit}")