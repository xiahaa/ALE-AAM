# Risk worksheet

For each of A/B/C calculate six raw scores in [0,1]: collision, terrain,
population exposure, weather, noise, and energy. Use weights 0.30, 0.10, 0.20,
0.15, 0.10, 0.15. `weighted_score = raw_score * weight`; the six weighted
scores sum to the route total. Write six dimension rows plus one TOTAL row per
route (21 rows). Select exactly one route, and make route_final.geojson byte-level
geometry-equivalent to that candidate. Do not invent measurements not derivable
from the staged GIS and submitted routes.
