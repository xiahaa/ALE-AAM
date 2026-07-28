# Hong Kong Kowloon Urban Drone Logistics

This is a benchmark simulation, not a real flight authorization. The 50–150 m
AGL envelope is a hypothetical advanced-operations permission; do not describe it
as the general legal limit.

Use only `[longitude, latitude]`. Inspect `gis/task.json`, then create three
materially different candidates: A shortest direct, B conservative with double
horizontal clearance, and C `low_noise`. Recompute risk from your own
submitted routes and select the lowest defensible total-risk route.

`task.json.planning_extent` is the authoritative structured-data boundary. All
submitted coordinates must remain inside it; any basemap visible beyond it is
visual context only and has no DEM, building, population, weather, or scoring data.

Deliver exactly six files in `output/`: `route_a.geojson`, `route_b.geojson`,
`route_c.geojson`, `route_final.geojson`, `risk_assessment.csv`, and
`emergency_response_plan.md`. The CSV has one header plus exactly 21 data rows.
Every waypoint has both `altitude_m_agl` and `altitude_m_msl`.
