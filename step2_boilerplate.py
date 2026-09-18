import pandas as pd
import glob

files = sorted(glob.glob('notices/*.csv'))
notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
notices['body'] = notices['body'].astype(str)

# --- Search for boilerplate markers mentioned in portal_profiles.md ---
markers = ['NATIONAL PROCUREMENT AGGREGATION SERVICE',
           'STATE PROCUREMENT CELL',
           'NPAS', 'SPC', 'Corrigendum', 'CORRIGENDUM',
           'Disclaimer', 'DISCLAIMER']

for m in markers:
    hits = notices['body'].str.contains(m, case=False, regex=False)
    print(f"{m:50s}  -> {hits.sum():5d} notices")

# --- How many distinct "first 200 chars" are there? (a proxy for template) ---
print("\n" + "=" * 60)
print("First 100 chars — most common prefixes")
print("=" * 60)
notices['prefix100'] = notices['body'].str[:100]
print(notices['prefix100'].value_counts().head(10))

# --- Search for 'Corrigendum' in title ---
print("\n" + "=" * 60)
print("Titles starting with Corrigendum")
print("=" * 60)
corr = notices['title'].str.lower().str.startswith('corrigendum')
print(f"Count: {corr.sum()}")
if corr.sum() > 0:
    print(notices[corr][['notice_id', 'portal_id', 'title', 'closing_date']].head(20).to_string())

# --- Estimated value ranges ---
print("\n" + "=" * 60)
print("Estimated value")
print("=" * 60)
print(notices['estimated_value'].describe())
print(f"\nZeros/negatives: {(notices['estimated_value'] <= 0).sum()}")
print(f"Duplicated values (likely re-publishes): {notices['estimated_value'].duplicated().sum()}")

# --- published_at / closing_date format ---
print("\n" + "=" * 60)
print("Date formats")
print("=" * 60)
print(f"published_at sample: {notices['published_at'].head(3).tolist()}")
print(f"closing_date sample: {notices['closing_date'].head(3).tolist()}")