import pandas as pd
import glob, os

BASE = r"C:\Users\ub02-glab-042\Desktop\Punarvasu_T_B\data_2\data_2"
files = sorted(glob.glob(os.path.join(BASE, 'notices', '*.csv')))
notices = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
notices['body'] = notices['body'].astype(str)

npas = notices[notices['body'].str.contains('NATIONAL PROCUREMENT AGGREGATION SERVICE', regex=False)]
spc  = notices[notices['body'].str.contains('STATE PROCUREMENT CELL', regex=False)]

print("=" * 80)
print(f"ONE FULL NPAS BODY  ({len(npas)} notices total)")
print("=" * 80)
print(npas['body'].iloc[0])

print("\n\n")
print("=" * 80)
print(f"ONE FULL SPC BODY  ({len(spc)} notices total)")
print("=" * 80)
print(spc['body'].iloc[0])