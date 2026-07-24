# Routing guidelines

- A: shortest feasible direct candidate.
- B: conservative safety candidate; clearance multiplier is exactly 2.0.
- C: `low_noise` for this scenario.
- All routes must avoid RFZ polygons, respect building height plus 15 m vertical
  clearance, remain in the 50–150 m AGL and 5–18 m/s envelopes, fit battery
  capacity, start/end exactly at task.json coordinates, and differ materially.
- `silas-maptool validate` checks public schema and explicit constraints only; it
  is not a reference-answer or grading command.
