import pandas as pd
import glob

files = sorted(glob.glob('notices/*.csv'))
notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
notices['body'] = notices['body'].astype(str)

# --- Look at one body per key portal ---
key_portals = ['P001', 'P002', 'P003', 'P004', 'P005', 'P006', 'P094', 'P136']
for pid in key_portals:
    sub = notices[notices['portal_id'] == pid]
    if len(sub) == 0:
        continue
    print("=" * 80)
    print(f"PORTAL {pid}  ({len(sub)} notices)")
    print("=" * 80)
    print(sub['body'].iloc[0][:2500])
    print()