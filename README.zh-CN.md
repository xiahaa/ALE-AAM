# ALE-AAM

[English](README.md) | 中文

ALE-AAM 是面向 [Agents' Last Exam（ALE）](https://agents-last-exam.org/) 香港低空
物流任务的跨平台、离线优先 GIS 工具。使用者和 agent 可以加载任务场景、查看运行
环境、绘制和编辑候选航线、导出 GeoJSON，并校验规定的交付文件。

仓库包含地图工具和三个可以独立上传的 ALE 任务：

| 任务 | 场景 |
|---|---|
| `urban_drone_logistics` | 香港九龙高密度城市物流 |
| `cross_sea_drone_logistics` | 香港南部跨海物流 |
| `emergency_blood_transport` | 港岛紧急血液运输 |

> 本项目仅用于基准评测和模拟，不是真实飞行许可、调度服务或航空安全运行系统。

## 功能

- 从本地场景目录加载确定性的任务 GIS。
- 展示地形、3D 建筑、限制空域、人口密度、天气和应急点图层。
- 查询任务范围内任意位置的结构化环境信息。
- 使用随任务提供的香港地政总署底图离线工作。
- 分别绘制、拖动和编辑 A、B、C 三条候选航线。
- 设置航点 AGL 高度和速度，并从 DEM 取得 MSL 高度。
- 使用 `[经度, 纬度]` 坐标导出标准 GeoJSON。
- 校验公开航线格式和六文件交付合同。
- 支持 Windows x64、Ubuntu x64、Intel Mac 和 Apple Silicon Mac。

## 下载文件

打开仓库的 **Actions** 页面，进入成功的 **ALE-AAM package** 工作流，可以下载：

| Artifact | 用途 |
|---|---|
| `ale-aam-maptool-1.0.0-universal-wheel` | 适用于全部支持平台、CPython 3.10–3.13 的地图工具 |
| `ale-aam-ubuntu-py312-wheelhouse` | ALE Ubuntu/Python 3.12 的完整离线安装包 |
| `ale-aam-urban-drone-logistics-base` | 城市物流任务上传包 |
| `ale-aam-cross-sea-drone-logistics-base` | 跨海物流任务上传包 |
| `ale-aam-emergency-blood-transport-base` | 紧急运血任务上传包 |

三个任务 artifact 都只包含一个任务，可以分别上传。提交前不要把三个任务 ZIP 合并。

## 安装地图工具

地图工具支持 CPython 3.10、3.11、3.12 和 3.13。安装脚本会创建项目内 `.venv`，
不需要管理员权限。

### 联网安装依赖

下载并解压 `ale-aam-maptool-1.0.0-universal-wheel`，把 wheel 放入
`ale_aam_maptool/dist/`。

Windows PowerShell：

```powershell
cd ale_aam_maptool
powershell -ExecutionPolicy Bypass -File .\install.ps1
.\run.cmd doctor --json
```

Ubuntu 或 macOS：

```bash
cd ale_aam_maptool
sh install.sh
./run.sh doctor --json
```

### 完全离线安装

把地图工具及所有依赖 wheel 放入 `ale_aam_maptool/wheelhouse/`，然后运行相同的安装
脚本。ALE Ubuntu artifact 已经包含 Python 3.12 所需的完整 wheelhouse。

健康检查成功时会输出包含 `"ok": true` 的 JSON。

## 快速开始

仓库内提供了一个小型、确定性的示例场景。

Windows：

```powershell
cd ale_aam_maptool
.\run.cmd inspect --scenario .\sample_scenario --json
.\run.cmd serve --scenario .\sample_scenario --host 127.0.0.1 --port 8000
```

Ubuntu 或 macOS：

```bash
cd ale_aam_maptool
./run.sh inspect --scenario ./sample_scenario --json
./run.sh serve --scenario ./sample_scenario --host 127.0.0.1 --port 8000
```

在浏览器打开 `http://127.0.0.1:8000/`。处理正式任务时，把 `sample_scenario` 换成
任务提供的 `input/gis` 目录。

服务启动时只绑定指定场景，网页请求不能选择服务器上的任意目录。

## 网页操作流程

1. 选择随场景提供的离线底图。
2. 按需显示环境图层。
3. 使用“查看”模式点击地图，读取地形、天气、人口、建筑、空域和应急点信息。
4. 选择候选路线 A、B 或 C；当前浏览器会分别保存三条路线的草稿。
5. 选择“画航点”，点击地图添加中间航点，拖动标记调整路线。
6. 编辑每个航点的 AGL 高度和速度。
7. 分别导出 `route_a.geojson`、`route_b.geojson` 或 `route_c.geojson`。
8. 按任务说明完成风险评估、最终路线和应急方案。

黄色虚线框是任务的有效分析范围。底图可以在框外提供额外的视觉参考，但结构化
查询和航点必须位于框内。

## 命令行接口

```text
doctor --json
inspect --scenario DIR --json
validate --scenario DIR --output DIR
basemap inspect --scenario DIR
basemap verify --pack FILE.mbtiles
serve --scenario DIR --host 127.0.0.1 --port 8000
```

示例：

```bash
ale-aam-maptool doctor --json
ale-aam-maptool inspect --scenario input/gis --json
ale-aam-maptool validate --scenario input/gis --output output
ale-aam-maptool basemap inspect --scenario input/gis
ale-aam-maptool serve --scenario input/gis --host 127.0.0.1 --port 8000
```

机器可读命令成功时向 stdout 输出 JSON，诊断和错误信息写入 stderr。

## 本地 HTTP API

| 方法 | 接口 | 用途 |
|---|---|---|
| GET | `/v1/health` | 服务健康状态和软件版本 |
| GET | `/v1/scenario` | 当前场景、任务范围、飞机和约束 |
| GET | `/v1/layers` | 图层清单 |
| GET | `/v1/layers/{id}` | 矢量 GeoJSON |
| GET | `/v1/layers/{id}/preview` | 确定性栅格预览 |
| GET | `/v1/environment?lon=&lat=` | 查询指定位置环境 |
| GET | `/v1/basemaps` | 可用底图清单 |
| GET | `/v1/basemaps/{id}/{z}/{x}/{y}.png` | 经过校验的底图瓦片 |
| POST | `/v1/validate` | 校验单条 GeoJSON Feature |

## 场景内容

每个任务 input 包含：

- `task_prompt.md` 和 `routing_guidelines.md`；
- `tool_usage.md` 和 `output_contract.json`；
- 风险评估量表和应急规划手册；
- 记录数据来源、CRS、获取日期、转换步骤和 SHA-256 的 `source_manifest.json`；
- 描述任务、飞机、约束、图层和路线目标的 `gis/task.json`；
- 5 m 地形、建筑高度、限制空域、人口、天气、应急点和离线底图。

GeoJSON 和全部机器接口统一使用 `[经度, 纬度]`。航点高度同时包含
`altitude_m_agl` 和 `altitude_m_msl`。

## 任务交付文件

ALE 提交必须正好包含六个文件：

```text
route_a.geojson
route_b.geojson
route_c.geojson
route_final.geojson
risk_assessment.csv
emergency_response_plan.md
```

每条候选路线必须：

- 是带有 `LineString` 几何的 GeoJSON `Feature`；
- 至少包含五个坐标；
- 从任务起点开始并在任务终点结束；
- 位于声明的任务范围内；
- 带有与坐标一一对应的 AGL 高度、MSL 高度和速度记录；
- 满足高度、空域、建筑净空、速度和能耗约束；
- 对应候选路线 A、B 或 C 指定的任务目标。

风险 CSV 对每条候选路线包含六个风险维度和一个总分行，共 21 行数据。应急方案必须
遵循场景手册并覆盖三级故障。

提交前执行公开校验：

```bash
ale-aam-maptool validate --scenario input/gis --output output
```

## 底图与密钥

随任务提供的香港 MBTiles 不需要网络或 API 密钥。需要可选在线底图时，把
`.env.example` 复制为 `.env` 并在本地配置：

```text
ALE_AAM_BASEMAP=auto
ALE_AAM_TIANDITU_TOKEN=...
ALE_AAM_MAPBOX_TOKEN=...
ALE_AAM_MAPBOX_STYLE=mapbox/streets-v12
```

`.env` 只能保存在本地。不得提交密钥、把密钥写入 JavaScript、放入任务包或通过 API
响应暴露。ALE 执行应使用随任务交付的离线底图。

## 验证

在仓库根目录执行：

```bash
python -m pip install "./ale_aam_maptool[test]"
python -m pytest ale_aam_maptool/tests
node --check ale_aam_maptool/ale_aam_maptool/web/app.js
```

GitHub Actions 还会在 Windows、Ubuntu、Intel macOS、Apple Silicon macOS 以及所有
支持的 Python 版本上安装测试 wheel。

## 数据与许可

每个任务的 `source_manifest.json` 记录数据来源和校验值。离线底图署名为“Map from
Lands Department, HKSAR Government”，其使用受 DATA.GOV.HK 条款约束。项目许可
和第三方声明见 `LICENSE` 与 `ale_aam_maptool/THIRD_PARTY_NOTICES.md`。

在授权的提交流程之外分发任务包前，应确认相关源数据的再分发条款。

## 常见问题

- **没有底图：**选择随任务提供的香港地政总署离线底图。部分网络可能无法访问可选
  在线服务。
- **某个位置不能查询或添加航点：**把该位置移入黄色任务范围框。
- **GeoJSON 导出提示缺少 MSL 高度：**该航点没有有效地形采样；移回任务范围后重试。
- **校验提示缺少文件：**`validate` 检查完整的六文件输出目录。
- **离线安装失败：**确认 `wheelhouse/` 中同时存在地图工具 wheel 和全部平台兼容的
  依赖 wheel。
