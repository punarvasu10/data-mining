Question 2 — Twelve Thousand Tenders, Wearing Disguise
========================================================

Files:
  answers.md            – full writeup (a-e + stable IDs)
  pipeline.py           – Section A evidence (signal, MinHash, LSH, error)
  section_b3.py         – Section B evidence (DB, access path, distribution, mitigation)
  evidence.py           – prints every measurement, sections a-e
  evidence_output.txt   – captured output (screenshots were taken from here)
  boilerplate_dump.txt  – examples of NPAS/SPC boilerplate

Headline results:
  Signal:  Name-of-Work line, normalized. Jaccard on word 3-shingles.
           same mean=1.000, different mean=0.030. Clean separation.
  Reduced form: MinHash-128. mean abs err = 0.0022, p95 = 0.0156.
  Retrieval:   LSH 32x4. P(retrieve|s=0.8) = 0.9999.
  Access:      B-tree on lsh_bands.band_hash. 0.064s / 1000 lookups
               vs 9.891s full scan (155x).
  Distribution: median candidates = 283, max = 765.
                top 1% of notices contribute 2.5% of candidate pairs.
  Mitigation:  cap candidate list at 30 per notice.
               3.49M pairs -> 357k pairs (-89.8%).
               recall(same) unchanged at 1.000, fp_rate 0.027 -> 0.006.
  Stable IDs:  SHA1(signal)[:12]. 5,194 cards / 12,000 notices, 2.31x merge.

Budget: 20 min/night.
  Full pipeline per run: ~4 min for 12k notices on one machine
  (signal 0.1s, MinHash 1.5s, LSH 1.1s, DB insert 6.7s,
   candidate retrieval ~25s with cap=30, pairwise scoring ~20s).
  Headroom for 2x corpus growth.