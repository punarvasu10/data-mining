import pandas as pd
import glob, os

print("=" * 60)
print("LABELS")
print("=" * 60)
labels = pd.read_csv('labelled_pairs.csv')
print(f"Total pairs: {len(labels)}")
print(f"\nLabel distribution:")
print(labels['label'].value_counts())
print(f"\nAs fractions:")
print(labels['label'].value_counts(normalize=True).round(4))
print(f"\nAdjudicated by:")
print(labels['adjudicated_by'].value_counts())
print(f"\nDate range: {labels['adjudicated_on'].min()} -> {labels['adjudicated_on'].max()}")

print("\n" + "=" * 60)
print("LOADING NOTICES (CSV)")
print("=" * 60)
files = sorted(glob.glob('notices/*.csv'))
print(f"Found {len(files)} CSV files")
for f in files:
    df = pd.read_csv(f)
    print(f"  {f}: {df.shape}")

notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)

print(f"\nShape: {notices.shape}")
print(f"\nColumns and dtypes:")
print(notices.dtypes)
print(f"\nFirst row:")
print(notices.iloc[0])

print("\n" + "=" * 60)
print("BODY LENGTHS")
print("=" * 60)
lengths = notices['body'].astype(str).str.len()
print(lengths.describe())
print(f"\nPercentiles:")
for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
    print(f"  p{p}: {lengths.quantile(p/100):.0f}")

print("\n" + "=" * 60)
print("PORTAL DISTRIBUTION (top 20)")
print("=" * 60)
print(notices['portal_id'].value_counts().head(20))

print("\n" + "=" * 60)
print("A SAMPLE BODY (first 3000 chars)")
print("=" * 60)
print(str(notices['body'].iloc[0])[:3000])

print("\n" + "=" * 60)
print("CHECK: are all label notice_ids in notices?")
print("=" * 60)
label_ids = set(labels['notice_id_a']) | set(labels['notice_id_b'])
corpus_ids = set(notices['notice_id'])
missing = label_ids - corpus_ids
print(f"Label IDs: {len(label_ids)}")
print(f"In corpus: {len(label_ids & corpus_ids)}")
print(f"Missing from corpus: {len(missing)}")
if missing:
    print(f"  Examples: {list(missing)[:10]}")

print("\n" + "=" * 60)
print("TRUTH FOLDER")
print("=" * 60)
for root, dirs, fs in os.walk('.truth'):
    for f in fs:
        p = os.path.join(root, f)
        print(f"  {p}  ({os.path.getsize(p)} bytes)")