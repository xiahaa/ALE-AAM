# ALE-AAM 1.0.0 最终版说明

[English documentation](README.md) | 中文说明

ALE-AAM 是用于 Agents' Last Exam（ALE）三个香港低空物流任务的最终离线 GIS
查看与人工航线编辑工具。工具负责加载任务场景、展示结构化环境图层、查询指定位置、
人工绘制和编辑 A/B/C 三条候选航线、导出 GeoJSON，以及检查公开输出合同。

最终版有意禁用了自动规划。工具中不存在 `plan`、`plan-all` CLI 命令，不存在
`/v1/plan` HTTP 接口，不公开 Python 自动规划 API，wheel 中也不再包含 JPS 原生
扩展。这样可以保留基准任务的推理难度：agent 必须理解 GIS 数据和显式约束，自行
构造三条候选路线。

本项目仅用于基准测试、模拟和评测，不是真实飞行许可、调度系统或航空安全系统。

## 1. 最终仓库内容

```text
ALE-AAM/
├── README.md / README.zh-CN.md       最终英文、中文说明
├── ale_aam_maptool/                  跨平台公开工具
│   ├── ale_aam_maptool/              Python 包和离线 Web UI
│   ├── sample_scenario/              确定性 smoke 测试场景
│   ├── scripts/                      仅保留发布验收脚本
│   ├── tests/                        最终能力和 API 测试
│   ├── install.ps1 / install.sh
│   ├── run.cmd / run.sh
│   └── pyproject.toml
├── ALE_v0.2/                         正式 ALE 任务唯一来源
│   ├── urban_drone_logistics/
│   ├── cross_sea_drone_logistics/
│   ├── emergency_blood_transport/
│   ├── _private/evaluator.py
│   ├── scripts/stage_release.py
│   └── tests/
├── data/                             已审查的空域源数据快照
└── .github/workflows/                构建和跨平台 smoke CI
```

开发期数据生成器、旧自动规划代码、CMake/JPS 源码、旧说明和评审记录均保存在本地
且被 Git 忽略的 `legacy/` 目录。它们不会进入 Git、wheel 或 ALE 上传包。

## 2. 正式任务与上传模型

`ALE_v0.2` 是最终任务的唯一来源，不是只用于开发工具的目录。Git 仓库将三个任务
放在一起是为了统一维护；ALE 上传时，它们是三个独立的任务 ID，每个任务只有一个
公开 `base` variant：

| 任务 ID | Base 场景 |
|---|---|
| `transport_safety/urban_drone_logistics` | 香港九龙高密度城市物流 |
| `transport_safety/cross_sea_drone_logistics` | 香港南部跨海物流 |
| `transport_safety/emergency_blood_transport` | 港岛紧急血液运输 |

每个任务源目录都有正式的 `task_card.json`、`main.py`、`input/` 和隐藏
`reference/`。发布脚本会把统一源码转换成三个互相独立、可单独上传的目录和 ZIP，
符合 ALE 当前的[任务包规范](https://agents-last-exam.org/docs/ale/pages/add-task.html)
和[数据分阶段注入规范](https://agents-last-exam.org/docs/ale/pages/tasks.html)。

不要再使用“`ALE_v0.1/input` + 手动加入新工具”的组合。v0.1 是历史版本，数据、
输出合同和打包方式均已过期。

## 3. 支持平台与 wheel

最终工具是纯 Python 通用 wheel：

```text
ale_aam_maptool-1.0.0-py3-none-any.whl
```

支持 CPython 3.10–3.13、Windows x64、Ubuntu x64、macOS Intel 和 macOS
Apple Silicon。普通用户不需要 CMake、C++ 编译器、Homebrew、apt 或 MSVC。
构建完全离线 wheelhouse 时，Rasterio、NumPy 等第三方依赖仍需准备相应平台的
预编译 wheel。

GitHub Actions 生成两个关键 artifact：

- `ale-aam-maptool-1.0.0-universal-wheel`：Windows、Ubuntu、Intel Mac 和
  Apple Silicon Mac 共用。
- `ale-aam-ubuntu-py312-wheelhouse`：正式 ALE Ubuntu/Python 3.12 离线安装包，
  包含工具及全部依赖。
- `ale-aam-urban-drone-logistics-base`：仅城市物流任务的上传 ZIP。
- `ale-aam-cross-sea-drone-logistics-base`：仅跨海物流任务的上传 ZIP。
- `ale-aam-emergency-blood-transport-base`：仅紧急运血任务的上传 ZIP。

在 GitHub 仓库的 **Actions** 页面等待 `ALE-AAM final package` 工作流成功后下载。

## 4. 安装

普通安装时，把通用 wheel 放到 `ale_aam_maptool/dist/`。完全离线安装时，把工具
和所有依赖 wheel 放到 `ale_aam_maptool/wheelhouse/`。

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
sh run.sh doctor --json
```

安装脚本会在项目内创建 `.venv/`。`doctor` 应包含：

```json
{
  "ok": true,
  "version": "1.0.0",
  "capabilities": {
    "inspect_environment": true,
    "manual_route_editing": true,
    "geojson_export": true,
    "automatic_planning": false
  }
}
```

## 5. 启动离线 Web UI

Windows：

```powershell
.\run.cmd serve --scenario ..\ALE_v0.2\urban_drone_logistics\input\gis --host 127.0.0.1 --port 8000
```

Ubuntu/macOS：

```bash
./run.sh serve --scenario ../ALE_v0.2/urban_drone_logistics/input/gis --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/`。服务启动时只绑定命令中指定的场景，网页不能读取
服务器上的任意路径。

### 人工航线工作流

1. 选择场景自带的香港地政总署离线底图。
2. 按需显示建筑、空域、天气、人口、地形和应急点图层。
3. 使用“查看”模式点击地图，读取该位置的结构化环境信息。
4. 在航线区选择 A、B 或 C。三条路线在当前页面中分别保存独立草稿。
5. 切换到“画航点”，点击地图添加中间航点；拖动航点调整位置，并填写 AGL 高度
   和速度。
6. 导出当前候选路线，文件名分别为 `route_a.geojson`、`route_b.geojson` 或
   `route_c.geojson`。
7. 依次完成另外两条路线，再按任务合同制作 `route_final.geojson`、风险 CSV 和
   应急响应方案。

黄色虚线框是 `task.json.planning_extent`。结构化查询和航点必须位于框内。离线
底图额外扩展了 20% 作为视觉参考，框外像素不是规划或评分数据。所有机器接口统一
使用 `[经度, 纬度]`，即 `[longitude, latitude]`。

## 6. 可选在线底图与密钥保密

任务自带的香港 MBTiles 不需要密钥，断网也可工作。天地图和 Mapbox 仅作为可选的
服务端代理底图。

将 `.env.example` 复制为 `.env` 后在本机填写：

```text
ALE_AAM_BASEMAP=auto
ALE_AAM_TIANDITU_TOKEN=...
ALE_AAM_MAPBOX_TOKEN=...
ALE_AAM_MAPBOX_STYLE=mapbox/streets-v12
```

禁止把 `.env` 提交到 Git、把密钥写入 JavaScript、把密钥放入 ALE 上传包，或通过
`/v1/basemaps` 返回密钥。Git 已忽略 `.env` 和相关 secret 文件。正式 ALE 执行必须
使用随任务交付的离线底图，不能依赖在线服务。

## 7. 最终 CLI 与 HTTP 合同

CLI 只保留：

```text
doctor --json
inspect --scenario DIR --json
validate --scenario DIR --output DIR
basemap inspect --scenario DIR
basemap verify --pack FILE.mbtiles
serve --scenario DIR --host 127.0.0.1 --port 8000
```

最终版没有 `plan`、`plan-all` 或规划栅格命令。

HTTP API：

| 方法 | 接口 | 用途 |
|---|---|---|
| GET | `/v1/health` | 版本和服务健康状态 |
| GET | `/v1/scenario` | 当前绑定场景及边界 |
| GET | `/v1/layers` | 图层清单 |
| GET | `/v1/layers/{id}` | 矢量 GeoJSON |
| GET | `/v1/layers/{id}/preview` | 确定性栅格预览 |
| GET | `/v1/environment?lon=&lat=` | 查询指定位置环境 |
| GET | `/v1/basemaps` | 不泄漏密钥的底图清单 |
| GET | `/v1/basemaps/{id}/{z}/{x}/{y}.png` | 校验后的瓦片代理 |
| POST | `/v1/validate` | 校验单条 GeoJSON Feature |

`/v1/plan`、`/v1/plan-all` 和 `/v1/preview` 均不存在。

## 8. 场景数据与输出合同

每个正式 input 包括：

- `task_prompt.md`、`routing_guidelines.md`、`tool_usage.md`；
- `output_contract.json`、风险量表和应急规划手册；
- 记录来源和 SHA-256 的 `source_manifest.json`；
- `gis/task.json`、5 m DTM、3D 建筑、RFZ、人口密度、天气网格、应急点，以及
  限定范围的香港地政总署 MBTiles。

agent 必须交付六个文件：

```text
route_a.geojson
route_b.geojson
route_c.geojson
route_final.geojson
risk_assessment.csv
emergency_response_plan.md
```

每条路线至少有五个 `[经度, 纬度]` 坐标，起终点必须与任务一致，所有坐标必须在
`planning_extent` 内，每个航点都要提供 `altitude_m_agl`、`altitude_m_msl` 和
`speed_ms`。`validate` 只检查公开格式和显式硬约束，不会生成、修复、评分或选择路线。

## 9. 构建并验证最终 wheel

```bash
python -m pip install build
python -m build --wheel --outdir dist ale_aam_maptool
python -m pip install "ale_aam_maptool[test]"
python -m pytest ale_aam_maptool/tests ALE_v0.2/tests
node --check ale_aam_maptool/ale_aam_maptool/web/app.js
```

最终 wheel 文件名必须以 `py3-none-any.whl` 结尾。包含 `.so`、`.pyd`、`.dylib`、
JPS 模块或规划接口的 wheel 不是最终发布版。

## 10. 生成三个独立 ALE 上传包

先把 GitHub Actions 生成的 `ale-aam-ubuntu-py312-wheelhouse` 解压到本地
`wheelhouse/`，再运行：

```bash
python ALE_v0.2/scripts/stage_release.py \
  --wheelhouse wheelhouse \
  --out ALE_v0.2/dist/ale-aam-final
```

将得到三个独立压缩包：

```text
ale-aam-urban_drone_logistics-base.zip
ale-aam-cross_sea_drone_logistics-base.zip
ale-aam-emergency_blood_transport-base.zip
```

每个 ZIP 只含一个任务：

```text
tasks/transport_safety/_private/evaluator.py
tasks/transport_safety/<task>/main.py
tasks/transport_safety/<task>/task_card.json
task_data/transport_safety/<task>/base/input/
task_data/transport_safety/<task>/base/software/wheelhouse/
task_data/transport_safety/<task>/base/reference/
release_manifest.json
```

ALE 在 agent 开始前注入 `input/` 和 `software/`，只能在 agent 完成后注入
`reference/`。禁止把 `reference` 放进 `input`，也不能把私有评分公式放到 agent
可见材料中。

通过 `--task <任务名>` 可以只生成一个任务。输出目录必须不存在，避免旧发布文件与
新文件静默混合。

## 11. 数据、许可与发布阻塞项

每个 `input/source_manifest.json` 都记录了数据 URL、获取日期、CRS、转换步骤和
SHA-256。离线地图署名为“Map from Lands Department, HKSAR Government”，使用和
再分发受 DATA.GOV.HK 条款约束。Leaflet 的 BSD-2-Clause 许可随 Web 资源交付；
项目许可和第三方声明见 `LICENSE` 与 `THIRD_PARTY_NOTICES.md`。

2026-07-24 eSUA/RFZ 快照已固定哈希并裁剪到各任务，但其再分发条款仍是正式发布的
阻塞项。即使 GitHub 仓库为私有，也应在对外上传任务前确认许可。

## 12. 常见问题

- **没有底图：**选择任务自带的香港地政总署离线底图。大陆网络可能无法访问可选
  在线服务。
- **某个位置不能查询或拖入航点：**该位置在黄色 `planning_extent` 外，只有视觉
  底图，没有任务结构化数据。
- **导出提示缺少 MSL 高度：**航点没有有效 DEM 采样；把航点移回任务范围后重试。
- **`validate` 提示缺文件：**它校验完整六文件输出目录，不只校验当前导出的路线。
- **找不到 `plan` 命令：**这是最终版的预期行为，自动规划已禁用，并非安装失败。
- **wheel 不兼容：**下载 `1.0.0` 通用 wheel，不要再使用旧的 `0.3.x` JPS 平台 wheel。
