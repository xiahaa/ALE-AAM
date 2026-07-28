# 香港空域数据快照

`hong_kong_airspace_20260724.zip` 是项目方于 2026-07-24 提供的香港空域数据包，供 ALE-AAM 离线演示、数据核验和场景制作使用。

- 坐标系：WGS84，经纬度顺序 `[longitude, latitude]`
- GeoJSON：`FeatureCollection`，包含 283 个 `Polygon`，属性 `type` 均为 `RFZ`
- ZIP 压缩方式：Store（未压缩）；ALE-AAM Web 页面可直接读取其中的 `GeoJSON/map.geojson`
- ZIP SHA-256：`b0cde3a908091359c1e10190d185ad74c60511cd943e5498b3c8bdd6b6f16614`
- `GeoJSON/map.geojson` SHA-256：`291738f88f5ccc7862f641b5cbaf92882fd031ff8f32d83e524525e1b961efa0`
- `KML/map.kml` SHA-256：`8517b22b5bf8c9b3c38e3e7735dcc725e931bf7dcd0f173b26b60328d92fed8a`

该快照的属性中包含各限制区的名称和生效时间。数据包本身没有随附完整的发布机构、下载地址和许可证，因此在完成来源核验前，不应在文档中将其描述为官方发布或用于真实飞行决策。

## 在 Web 页面中加载

1. 启动任意香港场景的 Web 服务。
2. 打开页面，在“加载数据”中选择 `hong_kong_airspace_20260724.zip`。
3. 打开新增的图层开关；点击限制区可查看原始属性。

ALE v0.2 已通过 `scripts/import_hk_airspace_snapshot.py` 校验上述 ZIP 哈希、
修复多边形拓扑并按各任务 DEM 范围确定性裁剪，生成每个场景的
`airspace_zones.geojson`。裁剪后城市、跨海、血运任务分别含 9、6、26 个 RFZ；
起终点均位于 RFZ 外，三种路线已重新执行可行性测试。跨海任务原终点落在
Cheung Chau Helipad RFZ 内，因此移动约 268 m 到已核验的区外位置。

这解决了“单个虚构禁飞区”造成的难度不足，但不消除来源许可问题：原 ZIP 未随附
完整许可证，公开发布前仍须确认再分发条款。任何这些数据都不得用于真实飞行决策。
