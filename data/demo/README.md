# Canonical Offline Demo Dataset

Use smartwealth_demo.csv for the rehearsed demo. It contains 24 ISO-dated synthetic transactions across all eight categories and exactly one deliberately ambiguous row, DEMO-023.

Expected offline behavior:

- 23 rows categorize deterministically with 0.99 confidence.
- DEMO-023 becomes Unknown with 0.20 confidence and pauses for human review.
- Entertainment is excluded from the immediate deduction total.
- Hardware is conservatively excluded because it requires depreciation analysis.
- All data is synthetic. Do not replace this file with client data.
