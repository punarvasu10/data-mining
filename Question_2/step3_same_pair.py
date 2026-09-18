import pandas as pd
import glob, os

BASE = r"C:\Users\ub02-glab-042\Desktop\Punarvasu_T_B\data_2\data_2"

files = sorted(glob.glob(os.path.join(BASE, 'notices', '*.csv')))
print(f"Found {len(files)} files")
notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
notices['body'] = notices['body'].astype(str)
notices = notices.set_index('notice_id')

labels = pd.read_csv(os.path.join(BASE, 'labelled_pairs.csv'))
same = labels[labels['label'] == 'same']
diff = labels[labels['label'] == 'different']

print("=" * 80)
print("SAME PAIRS ON DIFFERENT PORTALS")
print("=" * 80)
shown = 0
for _, row in same.iterrows():
    a, b = row['notice_id_a'], row['notice_id_b']
    if a not in notices.index or b not in notices.index:
        continue
    pa = notices.loc[a, 'portal_id']
    pb = notices.loc[b, 'portal_id']
    if pa != pb:
        print(f"\n>>> {a} ({pa})  vs  {b} ({pb})")
        print(f"\n--- {a} title ---")
        print(notices.loc[a, 'title'])
        print(f"\n--- {a} body (first 1500) ---")
        print(notices.loc[a, 'body'][:1500])
        print(f"\n--- {b} title ---")
        print(notices.loc[b, 'title'])
        print(f"\n--- {b} body (first 1500) ---")
        print(notices.loc[b, 'body'][:1500])
        shown += 1
        if shown >= 2:
            break

print("\n\n")
print("=" * 80)
print("DIFFERENT PAIR ON SAME PORTAL")
print("=" * 80)
shown = 0
for _, row in diff.iterrows():
    a, b = row['notice_id_a'], row['notice_id_b']
    if a not in notices.index or b not in notices.index:
        continue
    pa = notices.loc[a, 'portal_id']
    pb = notices.loc[b, 'portal_id']
    if pa == pb:
        print(f"\n>>> {a}  vs  {b}  (both {pa})")
        print(f"\n--- {a} title ---")
        print(notices.loc[a, 'title'])
        print(f"\n--- {a} body (first 1200) ---")
        print(notices.loc[a, 'body'][:1200])
        print(f"\n--- {b} title ---")
        print(notices.loc[b, 'title'])
        print(f"\n--- {b} body (first 1200) ---")
        print(notices.loc[b, 'body'][:1200])
        shown += 1
        if shown >= 2:
            break