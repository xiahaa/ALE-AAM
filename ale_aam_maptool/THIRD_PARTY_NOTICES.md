# Third-party notices

The native path planner is derived from `KumarRobotics/jps3d` and is distributed
under its BSD 3-Clause license. Its notice is preserved at
`vendor/jps3d/LICENSE`. Python dependencies retain their respective licenses.

Eigen headers are vendored under `vendor/eigen3` under MPL-2.0 (individual
files may carry the upstream BSD-3-Clause notice). The Debian copyright summary
used for this vendored copy is preserved as `vendor/eigen3/COPYING.README`.

Leaflet 1.9.4 is bundled under `ale_aam_maptool/web/vendor/leaflet` and is
distributed under the BSD 2-Clause license. Its upstream license is preserved
at `ale_aam_maptool/web/vendor/leaflet/LICENSE`. The Web interface loads this
copy locally and contains no CDN-hosted code, fonts, or tracking assets.

The scenario-local Hong Kong topographic MBTiles are bounded snapshots of the
key-free Lands Department Map API. Required attribution is “Map from Lands
Department, HKSAR Government”. Source, API documentation, acquisition time,
coverage and SHA-256 are recorded in each sibling manifest. Distribution and
reuse are subject to the DATA.GOV.HK Terms and Conditions.
