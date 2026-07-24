# ale-aam-maptool 0.2.0 与 ALE v0.2 详细使用手册

本文面向三类读者：

1. 在 Windows、Ubuntu 或 macOS 上安装和试用 `ale-aam-maptool` 的使用者。
2. 编写三条候选路线和六份 ALE 交付物的任务执行者。
3. 构建 wheel、整理任务包并在 ALE 中执行评测的维护者。

本文所有命令均从 `ale_aam_maptool` 或 `ALE_v0.2` 的目录根部执行。示例路径均为相对路径，不依赖某台机器上的绝对目录。

> 安全边界：本工具只用于基准测试、模拟规划、人工验收和演示，不是飞行授权、真实调度或实时航空安全系统。ALE 场景中的 150 m AGL 上限代表模拟的高级运营许可，不代表香港的一般法规限制。

## 1. 功能与版本

`ale-aam-maptool 0.2.0` 提供以下功能：

- 读取 DEM、三维建筑物、限制空域、人口、天气和应急点 GIS 图层。
- 使用原生 JPS 后端生成 A、B、C 三种低空路线。
- 导出带 AGL、MSL 高度及速度等属性的 GeoJSON。
- 检查场景、预览规划栅格、校验公开输出格式和显式硬约束。
- 提供稳定 CLI、版本化 HTTP API 和离线优先的 Web 界面；本地开发/演示可选天地图或 Mapbox 底图。
- Web 界面按“加载数据 → 查看环境 → 交互式画航线 → 导出 GeoJSON”工作，支持直接读取本地 GeoJSON 和包含未压缩 GeoJSON 的 ZIP。
- 使用平台 wheel 安装，普通用户不需要 C++ 编译器、MSVC、Homebrew、apt、sudo。

支持范围：

| 项目 | 支持范围 |
|---|---|
| Python | CPython 3.10、3.11、3.12、3.13 |
| Windows | x64 |
| Ubuntu | x64，正式 ALE 使用 Ubuntu/Python 3.12 |
| macOS | Intel x86_64、Apple Silicon arm64 |
| 网络 | 工具运行不需要网络，ALE 正式运行禁止联网 |

工具只检查公开格式和硬约束。它不包含隐藏参考答案、参考答案生成器、私有评分公式或直接生成最终答案的命令。

### 1.1 Web 航线编辑器

启动一个已经准备好的场景：

```bash
sh run.sh serve --scenario ./sample_scenario --host 127.0.0.1 --port 8000
```

Windows 使用：

```powershell
.\run.cmd serve --scenario .\sample_scenario --host 127.0.0.1 --port 8000
```

在浏览器打开 `http://127.0.0.1:8000` 后：

1. **加载数据**：页面自动显示场景声明的 DEM、3D 建筑、空域、气象、人口和应急点图层。每层可独立显示或隐藏。也可以选择本地 `.geojson`、`.json`，或包含 Store 模式 `.geojson` 的 `.zip`；文件只在浏览器内解析。
2. **查看环境**：用滚轮缩放，切换到“平移”后拖动地图；输入经纬度可定位。处于“查看”模式时点击地图，可读取该位置的地形高程、气象值、人口密度以及命中的建筑、空域和应急点属性。
3. **绘制航线**：页面先放入任务起点和终点。切换到“画航点”，点击地图添加中间航点；拖动圆点调整位置，在航点列表中设置 AGL 高度和速度，或删除航点。
4. **导出**：点击“导出 GeoJSON”，得到 `ale-aam-route.geojson`。几何类型为 `Feature/LineString`，坐标固定为 `[longitude, latitude]`，每个航点包含高度、速度，并在 DEM 有值时包含 `altitude_m_msl`。

Web 地图默认使用场景自身的数据渲染，不依赖 OSM、在线瓦片或 CDN，因此大陆网络、内网和断网环境下仍能显示。开发或演示时可按下一节启用天地图或 Mapbox；任何在线服务不可用时会自动回退到离线图层。仓库 `data/hong_kong_airspace_20260724.zip` 可直接作为本地空域叠加层加载。

### 1.2 可选在线底图与密钥保密

在线底图只用于本地开发、人工验收和演示。正式 ALE 任务保持离线，不配置任何在线底图密钥。

在 `ale_aam_maptool` 目录中复制示例配置：

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

Ubuntu/macOS：

```bash
cp .env.example .env
chmod 600 .env
```

编辑本机 `.env`，不要把真实值发到聊天、Issue、日志或 Git：

```dotenv
ALE_AAM_BASEMAP=tianditu-vector
ALE_AAM_TIANDITU_TOKEN=<本机天地图密钥>
ALE_AAM_MAPBOX_TOKEN=<本机 Mapbox access token>
ALE_AAM_MAPBOX_STYLE=mapbox/streets-v12
```

`ALE_AAM_BASEMAP` 可取：

| 值 | 含义 |
|---|---|
| `offline` | 离线场景图层，正式 ALE 和断网环境使用 |
| `tianditu-vector` | 天地图矢量底图与注记 |
| `tianditu-imagery` | 天地图影像底图与注记 |
| `mapbox-streets` | Mapbox 街道样式；可用 `ALE_AAM_MAPBOX_STYLE` 换成有权限的样式 |
| `mapbox-satellite` | Mapbox 卫星影像 |

重新启动 `serve` 后，页面“底图”列表只允许选择已经配置的服务。服务器使用固定白名单地址代理瓦片，浏览器只看到同源的 `/v1/basemaps/...` 地址，不会得到密钥；元数据接口、错误信息和日志也不返回密钥。`.gitignore` 已忽略 `.env`、`.env.local` 和 `*.secret.env`，仓库只提交空值的 `.env.example`。

这仍不等于供应商密钥可以不受约束地共享。请在天地图/Mapbox 管理后台限制允许来源、URL 或使用范围，按团队制度轮换和撤销；给同事分发真实 `.env` 时使用组织认可的密码管理器或加密通道。

## 2. 目录说明

发布给普通用户的最小目录如下：

```text
ale_aam_maptool/
├── install.ps1             # Windows 安装脚本
├── install.sh              # Ubuntu/macOS 安装脚本
├── run.cmd                 # Windows 命令入口
├── run.sh                  # Ubuntu/macOS 命令入口
├── wheelhouse/             # 完全离线安装时放 wheel 及其依赖
├── dist/                   # 单个正式发布 wheel 可放在此处或其子目录
└── sample_scenario/        # 示例场景
```

安装脚本会在项目内创建 `.venv/`。该目录可删除后重新安装，不应复制到另一台机器，也不应纳入发布包。

开发仓库还包括：

```text
ale_aam_maptool/
├── ale_aam_maptool/          # Python 包、HTTP 服务和离线 Web 资源
├── vendor/jps3d/           # BSD-3-Clause 原生 JPS 源码
├── tests/                  # 单元和接口测试
├── scripts/                # wheel 安装/运行 smoke
├── pyproject.toml
└── CMakeLists.txt

ALE_v0.2/
├── urban_drone_logistics/
├── cross_sea_drone_logistics/
├── emergency_blood_transport/
├── _private/evaluator.py
├── scripts/
└── tests/
```

## 3. 安装前检查

### 3.1 确认 Python 版本和架构

运行：

```text
python --version
python -c "import platform; print(platform.machine())"
```

Ubuntu/macOS 上如果命令名是 `python3`：

```text
python3 --version
python3 -c "import platform; print(platform.machine())"
```

Python 必须是 CPython 3.10 至 3.13。架构必须和 wheel 一致：

| 系统 | 常见架构输出 | 对应 wheel 标记示例 |
|---|---|---|
| Windows x64 | `AMD64` | `win_amd64` |
| Ubuntu x64 | `x86_64` | `manylinux_*_x86_64` |
| macOS Intel | `x86_64` | `macosx_*_x86_64` |
| macOS Apple Silicon | `arm64` | `macosx_*_arm64` |

wheel 文件名中的 `cp310`、`cp311`、`cp312`、`cp313` 分别对应 Python 3.10、3.11、3.12、3.13。例如，Python 3.12 不能安装 `cp313` wheel。

### 3.2 放置 wheel

有两种发布形式：

- 完全离线包：把 `ale_aam_maptool` 和所有依赖 wheel 放在 `wheelhouse/`。安装脚本使用 `--no-index`，不会访问 PyPI。
- 普通发布包：把与当前平台匹配的 `ale_aam_maptool` wheel 放在 `dist/` 或 `dist/` 的一级子目录。安装器可从 PyPI 获取声明的 Python 依赖。

正式 ALE 必须使用第一种形式，并且 `wheelhouse/` 中必须包含 Linux CPython 3.12 的 `ale_aam_maptool 0.2.0` wheel 及所有依赖。

## 4. 三平台安装

### 4.1 Windows x64

在 PowerShell 中进入 `ale_aam_maptool` 目录：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

如果机器有多个 Python，可显式指定解释器：

```powershell
$env:PYTHON_BIN = "C:\Path\To\Python312\python.exe"
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

安装成功后，最后一行会输出 `doctor` JSON。后续命令通过 `run.cmd` 执行：

```powershell
.\run.cmd doctor --json
```

### 4.2 Ubuntu x64

进入 `ale_aam_maptool` 目录：

```bash
PYTHON_BIN=python3.12 sh install.sh
sh run.sh doctor --json
```

如果系统默认 `python3` 已经是受支持版本，也可直接运行：

```bash
sh install.sh
sh run.sh doctor --json
```

正式 ALE 的安装由任务 `start()` 自动完成，使用 `--no-index --only-binary=:all:`，不需要也不允许使用 apt、sudo 或源码编译。

### 4.3 macOS Intel 或 Apple Silicon

先确保使用的 Python 架构和 wheel 一致。Apple Silicon 推荐使用原生 arm64 Python 和 arm64 wheel：

```bash
python3 --version
python3 -c 'import platform; print(platform.machine())'
PYTHON_BIN=python3 sh install.sh
sh run.sh doctor --json
```

无需安装 Homebrew。如果从压缩包解压后脚本没有执行权限，直接使用 `sh install.sh` 和 `sh run.sh ...` 即可。

Intel Python、Rosetta x86_64 Python 和 arm64 Python 不能混用 wheel。遇到 `incompatible architecture` 时，应更换 Python 或 wheel，不要尝试在用户机器上编译原生扩展。

正式 wheel 由 GitHub Actions 的 `ale-aam-maptool cross-platform wheels`
工作流生成。下载名为 `ale-aam-maptool-0.2.0-macos-wheels` 的 artifact，解压后根据
Python 和架构选择一个 wheel：

```text
Python 3.10 + Intel          cp310-...-x86_64.whl
Python 3.10 + Apple Silicon cp310-...-arm64.whl
Python 3.11 + Intel          cp311-...-x86_64.whl
Python 3.11 + Apple Silicon cp311-...-arm64.whl
Python 3.12 + Intel          cp312-...-x86_64.whl
Python 3.12 + Apple Silicon cp312-...-arm64.whl
Python 3.13 + Intel          cp313-...-x86_64.whl
Python 3.13 + Apple Silicon cp313-...-arm64.whl
```

将匹配的 wheel 放到对应目录，例如：

```text
dist/macos-arm64/ale_aam_maptool-0.2.0-cp312-...-arm64.whl
```

然后运行：

```bash
PYTHON_BIN=python3.12 sh install.sh
sh run.sh doctor --json
```

如果 CI 尚未生成首批 Mac artifacts，可以让一名维护者在相应架构的 Mac 上执行：

```bash
sh scripts/build_macos_wheels.sh
```

它会使用 cibuildwheel 生成本机架构的 Python 3.10 至 3.13 wheels 到
`dist/macos-arm64/` 或 `dist/macos-x86_64/`。这只是发布维护者的应急引导路径，需要
Xcode Command Line Tools 和网络；构建完成后应把 wheels 分发给普通用户，普通用户仍然
只运行 `install.sh`，不需要编译器。

## 5. 第一次运行

### 5.1 健康检查

Windows：

```powershell
.\run.cmd doctor --json
```

Ubuntu/macOS：

```bash
sh run.sh doctor --json
```

正常输出示例：

```json
{
  "machine": "AMD64",
  "native": {"api_version": "2", "available": true},
  "offline_web": true,
  "ok": true,
  "python_supported": true,
  "version": "0.2.0"
}
```

以下三个条件必须同时满足：

- `python_supported` 为 `true`。
- `native.available` 为 `true`。
- `offline_web` 为 `true`。

### 5.2 检查示例场景

Windows：

```powershell
.\run.cmd inspect --scenario .\sample_scenario --json
```

Ubuntu/macOS：

```bash
sh run.sh inspect --scenario ./sample_scenario --json
```

输出包含任务 schema、起终点、A/B/C 策略、栅格尺寸、分辨率、CRS、经纬度范围和图层声明。正式规划前应先执行一次 `inspect`。

### 5.3 生成三条示例路线

Windows：

```powershell
.\run.cmd plan-all --scenario .\sample_scenario --outdir .\output
```

Ubuntu/macOS：

```bash
sh run.sh plan-all --scenario ./sample_scenario --outdir ./output
```

此命令只生成：

```text
output/
├── route_a.geojson
├── route_b.geojson
└── route_c.geojson
```

它不会自动选择最终路线，不会生成风险表，也不会撰写应急方案。这是有意设计，避免公开工具泄漏或代替 agent 完成评测任务。

## 6. CLI 完整说明

Windows 使用 `.\run.cmd`，Ubuntu/macOS 使用 `sh run.sh`。下表省略了这个前缀。

稳定命令形状如下：

```text
doctor --json
inspect --scenario DIR --json [--resolution FLOAT]
plan --scenario DIR --route A|B|C --out FILE [--resolution FLOAT]
plan-all --scenario DIR --outdir DIR [--resolution FLOAT]
grid --scenario DIR --route A|B|C --out FILE [--resolution FLOAT]
validate --scenario DIR --output DIR [--resolution FLOAT]
serve --scenario DIR --host 127.0.0.1 --port 8000 [--resolution FLOAT]
```

| 命令 | 作用 | 主要参数 |
|---|---|---|
| `doctor --json` | 检查 Python、平台、原生后端和离线 Web 资源 | 无 |
| `inspect` | 读取并汇总场景 | `--scenario DIR --json [--resolution FLOAT]` |
| `plan` | 生成一条候选路线 | `--scenario DIR --route A\|B\|C --out FILE [--resolution FLOAT]` |
| `plan-all` | 生成 A、B、C 三条候选路线 | `--scenario DIR --outdir DIR [--resolution FLOAT]` |
| `grid` | 输出指定策略的规划占用栅格 PNG | `--scenario DIR --route A\|B\|C --out FILE [--resolution FLOAT]` |
| `validate` | 校验六份公开交付物及显式字段 | `--scenario DIR --output DIR [--resolution FLOAT]` |
| `serve` | 启动绑定场景的本地 HTTP/Web 服务 | `--scenario DIR [--host 127.0.0.1] [--port 8000] [--resolution FLOAT]` |

默认栅格分辨率为 5 m。改变分辨率会改变栅格尺寸、计算量和可能的路径细节。跨平台一致性验收时必须使用相同输入、相同版本和相同 `--resolution`。

### 6.1 单路线规划

```bash
sh run.sh plan \
  --scenario ./sample_scenario \
  --route B \
  --out ./output/route_b.geojson
```

成功后 stdout 只输出一个 JSON 对象，内容包括输出路径、路线名和距离、时长、能耗指标。

### 6.2 同时规划三条路线

```bash
sh run.sh plan-all \
  --scenario ./sample_scenario \
  --outdir ./output
```

### 6.3 输出规划栅格

```bash
sh run.sh grid \
  --scenario ./sample_scenario \
  --route C \
  --out ./output/grid_c.png
```

该 PNG 是离线规划栅格，不是在线地图截图。它适合排查建筑物、空域缓冲和策略造成的阻断。

### 6.4 校验完整交付物

```bash
sh run.sh validate \
  --scenario ./sample_scenario \
  --output ./output
```

公开校验器检查：

- 六个文件是否存在且非空。
- 三条候选路线是否为 `Feature/LineString`。
- 坐标是否是 WGS84 `[longitude, latitude]`。
- 起点、终点、`route_name`、航点数量是否一致。
- 每个航点的 AGL、MSL 和速度字段是否存在并满足显式范围。
- `risk_assessment.csv` 是否为一个表头加 21 行数据。
- `route_final.geojson` 是否声明选择 A、B 或 C。

它不会返回隐藏评测分数，也不会替 agent 生成风险值。

### 6.5 退出码与输出通道

| 退出码 | 含义 | 常见原因 |
|---|---|---|
| `0` | 成功 | 命令正常完成 |
| `2` | 配置或校验错误 | 缺文件、字段错误、坐标顺序错误、输出不完整 |
| `3` | 无可行路径 | RFZ/建筑缓冲阻断、硬约束过严、起终点不可达 |
| `4` | 原生后端错误 | wheel/架构不匹配、原生模块未加载、后端异常 |

成功的机器命令只向 stdout 写一个 JSON 对象。诊断信息和结构化错误写 stderr。因此可安全地保存 stdout：

```bash
sh run.sh inspect --scenario ./sample_scenario --json > inspect_result.json
```

## 7. A、B、C 路线含义

路线策略由场景 `task.json` 的 `route_profiles` 声明：

| 路线 | 固定语义 | 典型配置 |
|---|---|---|
| A | 最短直达 | `shortest_direct`，基础净空 |
| B | 保守安全 | 双倍水平净空，较保守的高度/速度 |
| C | 场景任务优化 | 城市低噪声、跨海风场/能耗、血液运输时间最优 |

ALE v0.2 三个正式场景中，C 的目标分别为：

| ALE 任务 | C 路线目标 |
|---|---|
| `urban_drone_logistics` | `low_noise` |
| `cross_sea_drone_logistics` | `wind_energy_optimized` |
| `emergency_blood_transport` | `time_optimal` |

A、B、C 必须在几何、目标、高度或速度等方面体现实质差异。把同一条路线复制三份不符合任务要求。

## 8. 场景数据格式

### 8.1 目录结构

一个完整场景通常包含：

```text
scenario/
├── task.json
├── dem.tif
├── buildings_3d.geojson
├── airspace_zones.geojson
├── population_density.tif     # 可选，由 task.json 声明
├── weather_grid.tif           # 可选，由 task.json 声明
└── emergency_sites.geojson    # 可选，由 task.json 声明
```

`task.json`、DEM、建筑和空域是规划所需核心文件。人口、天气、应急点是否存在由场景声明。

### 8.2 坐标和 CRS

- 所有 JSON/GeoJSON 机器接口统一使用 `[经度, 纬度]`，即 `[longitude, latitude]`。
- GeoJSON 坐标采用 WGS84。
- GeoTIFF 可以使用自身 CRS。工具读取后使用 `always_xy` 进行转换，并在本地 UTM 栅格中规划。
- 不要将 `[纬度, 经度]` 传入工具。数值可能仍在合法范围内，但会落到错误地点。

### 8.3 AGL 与 MSL

- `altitude_m_agl`：相对航点下方地面的高度。
- `altitude_m_msl`：相对平均海平面的高度。
- 一般关系为 `MSL = 地形高程 + AGL`。

两者不可互换。每个输出航点必须同时包含这两个字段。

### 8.4 建筑物高度

建筑 GeoJSON 可使用以下属性表达高度：

- `height_m`
- `height`
- `building:levels`
- `levels`

楼层数会按每层 3.5 m 换算。缺少上述字段时使用 `constraints.default_building_height_m`。

### 8.5 `task.json` 示例

```json
{
  "schema_version": "2.0",
  "mission": {
    "id": "example-mission",
    "name": "Example mission",
    "start": [114.1700, 22.3000],
    "goal": [114.1850, 22.3100],
    "environment": "urban"
  },
  "layers": {
    "dem": "dem.tif",
    "buildings": "buildings_3d.geojson",
    "airspace": "airspace_zones.geojson",
    "population": "population_density.tif",
    "weather": "weather_grid.tif",
    "emergency_sites": "emergency_sites.geojson"
  },
  "aircraft": {
    "model": "benchmark-multirotor",
    "cruise_speed_ms": 12,
    "max_speed_ms": 18,
    "cruise_power_w": 650,
    "battery_capacity_wh": 2200
  },
  "constraints": {
    "altitude_m_agl": {"min": 50, "max": 150},
    "speed_ms": {"min": 5, "max": 18},
    "vertical_clearance_m": 10,
    "horizontal_clearance_m": 20,
    "default_building_height_m": 25,
    "noise_sensitive_pop_percentile": 80
  },
  "route_profiles": {
    "A": {
      "objective": "shortest_direct",
      "strategy": "direct",
      "cruise_agl_m": 145,
      "speed_ms": 12,
      "clearance_multiplier": 1,
      "avoid_population": false
    },
    "B": {
      "objective": "conservative_safety",
      "strategy": "conservative",
      "cruise_agl_m": 100,
      "speed_ms": 10,
      "clearance_multiplier": 2,
      "avoid_population": false
    },
    "C": {
      "objective": "low_noise",
      "strategy": "mission_optimized",
      "cruise_agl_m": 120,
      "speed_ms": 11,
      "clearance_multiplier": 1.25,
      "avoid_population": true
    }
  }
}
```

## 9. 路线 GeoJSON 输出

单条路线是一个 GeoJSON `Feature`，几何类型为 `LineString`：

```json
{
  "type": "Feature",
  "geometry": {
    "type": "LineString",
    "coordinates": [
      [114.1700, 22.3000],
      [114.1720, 22.3010],
      [114.1760, 22.3040],
      [114.1810, 22.3080],
      [114.1850, 22.3100]
    ]
  },
  "properties": {
    "schema_version": "2.0",
    "route_name": "A",
    "strategy": "direct",
    "objective": "shortest_direct",
    "waypoints": [
      {
        "index": 0,
        "altitude_m_agl": 145.0,
        "altitude_m_msl": 162.0,
        "speed_ms": 12.0,
        "heading_deg": 42.5
      }
    ],
    "total_distance_m": 2000.0,
    "estimated_duration_s": 166.7,
    "estimated_energy_wh": 36.1,
    "population_hard_avoidance": false
  }
}
```

实际文件的 `waypoints` 数量必须与 `coordinates` 数量完全一致。上例只展示属性形状，不是有效的完整路线文件。

## 10. 完成 ALE 六份交付物

每个任务的 `output/` 必须恰好包含以下六份核心交付物：

```text
output/
├── route_a.geojson
├── route_b.geojson
├── route_c.geojson
├── route_final.geojson
├── risk_assessment.csv
└── emergency_response_plan.md
```

### 10.1 第一步：生成候选路线

在 ALE Ubuntu 环境中，`start()` 已经把工具安装到 `software/.venv`。任务执行者使用：

```bash
software/.venv/bin/ale-aam-maptool doctor --json
software/.venv/bin/ale-aam-maptool inspect --scenario input/gis --json
software/.venv/bin/ale-aam-maptool plan-all --scenario input/gis --outdir output
```

如果平台只提供 Python 模块入口，也可以：

```bash
software/.venv/bin/python -m ale_aam_maptool plan-all \
  --scenario input/gis \
  --outdir output
```

### 10.2 第二步：从自己的路线重算风险

风险表固定包含六个维度：

| 维度 | 含义 | 权重 |
|---|---|---:|
| `collision` | 限制空域、建筑物和净空相关风险 | 0.30 |
| `terrain` | 地形起伏和地形相关风险 | 0.10 |
| `population` | 人口暴露 | 0.20 |
| `weather` | 风场/天气暴露 | 0.15 |
| `noise` | 人口与速度相关的噪声暴露 | 0.10 |
| `energy` | 能耗相对电池能力 | 0.15 |

每个原始风险分 `raw_score` 在 `[0,1]`。值越低代表风险越低。必须基于 agent 自己提交的路线和场景 GIS 计算，不得照抄其他路线或虚构测量。

CSV 表头必须是：

```csv
route,dimension,raw_score,weight,weighted_score,total_score,selected
```

每条路线写六个维度行，再写一个 `TOTAL` 行。A、B、C 共 21 个数据行：

```csv
A,collision,<0到1>,0.30,<raw*weight>,,false
A,terrain,<0到1>,0.10,<raw*weight>,,false
A,population,<0到1>,0.20,<raw*weight>,,false
A,weather,<0到1>,0.15,<raw*weight>,,false
A,noise,<0到1>,0.10,<raw*weight>,,false
A,energy,<0到1>,0.15,<raw*weight>,,false
A,TOTAL,,,<六项加总>,<六项加总>,false
```

B、C 使用相同七行结构。数值字段必须填真实数字，不能保留尖括号占位符。要求：

- `weighted_score = raw_score * weight`。
- `total_score` 等于该路线六个 `weighted_score` 之和。
- 三条路线中恰好一条的 `selected` 为 `true`。
- 最终应选择可辩护的最低总风险路线。

### 10.3 第三步：生成最终路线

`route_final.geojson` 必须选择 A、B 或 C 中的一条，几何与被选候选路线一致。最稳妥做法是直接复制选中的候选文件。

Windows PowerShell，例如选择 B：

```powershell
Copy-Item .\output\route_b.geojson .\output\route_final.geojson
```

Ubuntu/macOS，例如选择 B：

```bash
cp output/route_b.geojson output/route_final.geojson
```

同时确认 `route_final.geojson` 中的 `properties.route_name` 为 `B`，并且风险表只有 B 被标为 `selected=true`。

### 10.4 第四步：撰写应急响应方案

`emergency_response_plan.md` 至少应包含：

1. 任务概述和按飞行阶段划分的路线分段。
2. L1、L2、L3 三级事件定义、升级条件和职责边界。
3. 至少五类不同故障的矩阵，列出故障、触发条件、行动、授权者和通信方式。
4. 主通信链路、备用通信链路、失联处置。
5. 指挥权、交接流程、恢复、记录和事后报告。
6. 至少三个经 GIS 核验的应急点。`site_id` 和 `[longitude, latitude]` 必须与 `input/gis/emergency_sites.geojson` 一致。
7. 与场景匹配的专属内容。

场景专属内容：

| 场景 | 必须覆盖的主题 |
|---|---|
| 香港九龙城市物流 | 开放空间、密集城市环境、行人警戒/隔离 |
| 香港南部跨海物流 | 水上迫降、海上救援、风况备用方案 |
| 港岛紧急血运 | 2 至 8°C 冷链、医院交接、时限和样本完整性 |

推荐结构：

```markdown
# 应急响应方案

## 1. 任务与路线分段
## 2. 指挥体系和通信
## 3. L1/L2/L3 分级
## 4. 故障矩阵
## 5. 备降/迫降点
## 6. 场景专属处置
## 7. 恢复、交接和报告
```

### 10.5 第五步：公开校验

```bash
software/.venv/bin/ale-aam-maptool validate \
  --scenario input/gis \
  --output output
```

只有输出中的 `"ok":true` 且进程退出码为 0，才表示公开格式校验通过。公开校验通过不等于隐藏评测满分。

## 11. 离线 Web 界面

启动服务时必须绑定一个场景：

Windows：

```powershell
.\run.cmd serve --scenario .\sample_scenario --host 127.0.0.1 --port 8000
```

Ubuntu/macOS：

```bash
sh run.sh serve --scenario ./sample_scenario --host 127.0.0.1 --port 8000
```

浏览器打开：

```text
http://127.0.0.1:8000/
```

Web 界面可以：

- 显示绑定场景信息和离线规划栅格。
- 单独规划 A、B 或 C。
- 同时规划三条路线并叠加显示。
- 导出当前浏览器中的路线为 `routes.geojson` FeatureCollection。

Web 导出的 FeatureCollection 主要用于查看和演示，不等同于 ALE 要求的六份独立交付物。正式任务仍应使用 CLI 生成 `route_a.geojson`、`route_b.geojson`、`route_c.geojson`。

页面资源、字体、样式和脚本均来自本地，不使用 CDN 或追踪服务。默认背景栅格来自绑定场景；启用天地图/Mapbox 时，只有后端瓦片代理访问供应商，浏览器不会接收供应商密钥。服务只能访问启动时绑定的场景，不接受网页传入任意服务器目录。在线底图失败时页面自动回退到离线场景图层。

## 12. HTTP API

服务基础地址示例为 `http://127.0.0.1:8000`。

| 方法 | 路径 | 请求 | 返回 |
|---|---|---|---|
| GET | `/v1/health` | 无 | 服务版本及场景绑定状态 |
| GET | `/v1/scenario` | 无 | 场景、范围、栅格、策略摘要 |
| GET | `/v1/preview?route=A` | 查询参数 A/B/C | PNG 规划栅格 |
| GET | `/v1/basemaps` | 无 | 可用底图、默认值、显示名称和署名；不含密钥 |
| GET | `/v1/basemaps/{provider}/{z}/{x}/{y}.png` | 白名单 provider 与有效瓦片坐标 | 同源代理瓦片；不可用时返回通用错误 |
| POST | `/v1/plan` | `{"route":"A","densify_interval_m":200}` | 单条 Feature 与指标 |
| POST | `/v1/plan-all` | 无请求体 | A/B/C Feature 与指标 |
| POST | `/v1/validate` | `{"feature":{...},"expected_route":"A"}` | 单个 Feature 的公开校验报告 |

### 12.1 curl 示例

```bash
curl http://127.0.0.1:8000/v1/health
curl http://127.0.0.1:8000/v1/scenario
curl "http://127.0.0.1:8000/v1/preview?route=C" --output preview_c.png
curl -X POST http://127.0.0.1:8000/v1/plan \
  -H "Content-Type: application/json" \
  -d '{"route":"C","densify_interval_m":200}'
curl -X POST http://127.0.0.1:8000/v1/plan-all
```

### 12.2 PowerShell 示例

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/health
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/scenario

$body = @{ route = "C"; densify_interval_m = 200 } | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/v1/plan `
  -ContentType "application/json" `
  -Body $body
```

`/v1/validate` 校验单个 GeoJSON Feature。CLI 的 `validate --output DIR` 校验整个六文件目录，两者用途不同。

## 13. ALE v0.2 任务使用

### 13.1 三个任务 ID

```text
transport_safety/urban_drone_logistics
transport_safety/cross_sea_drone_logistics
transport_safety/emergency_blood_transport
```

每个源任务包含：

```text
<task>/
├── main.py
├── task_card.json
├── input/
│   ├── task_prompt.md
│   ├── output_contract.json
│   ├── routing_guidelines.md
│   ├── risk_assessment_rubric.md
│   ├── emergency_planning_manual.md
│   ├── source_manifest.json
│   └── gis/
└── reference/
    └── anchors.json
```

源仓库中的 `reference/` 只供任务维护者和评测阶段使用。它绝不能出现在 agent 可见输入、软件目录或工作目录中。

### 13.2 `load/start/evaluate` 生命周期

- `load()`：返回任务描述、元数据和 `cpu-free-ubuntu` 运行要求。
- `start()`：幂等清空输出和运行期 reference 目录，验证输入，离线创建工具环境，执行 `doctor` 和 `inspect`，确认参考答案尚不可见。
- agent 阶段：agent 只能看到 `input/`、`software/` 和自己的 `output/`。
- reference staging：agent 完成后，由 ALE 基础设施注入 `reference/anchors.json`。
- `evaluate()`：对输出执行私有多解约束评测。缺失或损坏的 agent 输出只降低分数或得到 0，不应引发任务基础设施崩溃。

评测总结构为：文件与 schema 10%，路线约束与策略 35%，风险重算与最终选择 35%，应急方案 20%。隐藏 reference 保存专家基线、容差和已核验候选点，不要求路线贴合唯一 LineString。

### 13.3 生成/刷新任务源

在 `ALE_v0.2` 目录中：

```bash
python scripts/build_tasks.py
python scripts/refresh_official_sources.py
python -m pytest tests
```

说明：

- `build_tasks.py` 确定性重建三场景及任务文件。
- `refresh_official_sources.py` 用于维护者刷新固定日期的官方数据快照，需要网络，只能在任务发布前执行，不能在 agent 运行期间执行。
- 在以固定、许可明确的民航处 eSUA/CAD 导出替换当前 RFZ fixture 并更新 SHA-256 前，任务仍应视为有发布阻断项。
- 所有来源、许可、获取日期、CRS、转换步骤和 SHA-256 应在 `source_manifest.json` 中可核验。

### 13.4 制作 ALE 发布目录

先把 Linux CPython 3.12 的完整离线 wheelhouse 放到：

```text
ale_aam_maptool/wheelhouse/
```

然后在 `ALE_v0.2` 目录执行：

```bash
python scripts/stage_release.py
```

默认生成：

```text
ALE_v0.2/dist/ale-v0.2/
├── tasks/transport_safety/
│   ├── _private/evaluator.py
│   ├── urban_drone_logistics/
│   ├── cross_sea_drone_logistics/
│   └── emergency_blood_transport/
├── task_data/transport_safety/
│   ├── urban_drone_logistics/base/{input,software,reference}/
│   ├── cross_sea_drone_logistics/base/{input,software,reference}/
│   └── emergency_blood_transport/base/{input,software,reference}/
└── release_manifest.json
```

`stage_release.py` 不覆盖已有目标目录。需要保留旧包时可指定新输出目录：

```bash
python scripts/stage_release.py --out dist/ale-v0.2-build2
```

`release_manifest.json` 记录发布文件的大小和 SHA-256，交付前应保存并核对。

### 13.5 集成到 ALE 主仓库

以下步骤在 ALE 主仓库根部执行：

1. 将发布包的 `tasks/transport_safety/` 合并到 ALE 的 `tasks/transport_safety/`。
2. 将发布包的 `task_data/transport_safety/` 放到环境配置所指向的 task-data 根目录。
3. 新建任务清单，例如 `selected_tasks/ale_aam_v02.txt`：

```text
transport_safety/urban_drone_logistics
transport_safety/cross_sea_drone_logistics
transport_safety/emergency_blood_transport
```

4. 建立实验 YAML，例如：

```yaml
name: ale_aam_v02
agents:
  - configs/agents/dummy.yaml
environment: configs/environments/docker.yaml
tasks: selected_tasks/ale_aam_v02.txt
output:
  root: .logs/ale
concurrency: 1
wall_time_s: 14400
auto_resume: false
max_attempts: 1
cleanup_mode: delete
```

`agents` 和 `environment` 必须替换为评测团队实际使用的配置。对于官方 ALE 的 Docker 配置，`task_data_source: local:task-data` 表示宿主机 task-data 根目录通常为 ALE 根部的 `task-data/`，目录下面再接 `transport_safety/<task>/base/`。

先只做发现和配置检查：

```bash
uv run python -m ale_run run ale_aam_v02.yaml --dry-run
```

确认任务发现、wheelhouse、task-data 来源、输出目录和 agent 配置无误后再执行：

```bash
uv run python -m ale_run run ale_aam_v02.yaml
```

日志默认位于：

```text
.logs/ale/ale_aam_v02/
```

正式运行时，ALE 数据提供器必须先只 stage `input/` 和 `software/`，agent 结束后再 stage `reference/`。不要手工把完整 `base/` 直接挂载为 agent 可读目录。

## 14. 常见问题排查

### 14.1 安装器提示没有兼容 wheel

检查：

```text
python --version
python -c "import platform; print(platform.machine())"
```

然后确认 wheel 的 CPython 标记和平台标记匹配。常见错误是：

- Python 3.12 配了 `cp313` wheel。
- Apple Silicon arm64 Python 配了 x86_64 wheel。
- Windows x64 配了 Linux/macOS wheel。
- wheel 放在了安装器不会扫描的目录。

将 wheel 放入 `wheelhouse/`、`dist/` 或 `dist/` 的一级子目录后重新运行安装脚本。

### 14.2 `doctor` 中 `native.available=false` 或退出码 4

通常是 wheel/架构不匹配、错误版本的源码遮蔽了已安装包，或 `.venv` 已损坏。处理顺序：

1. 确认通过项目的 `run.cmd`/`run.sh` 执行，而不是另一个 Python。
2. 确认 wheel 与 Python/架构匹配。
3. 在保留发布文件的前提下重新创建项目 `.venv` 并再次安装。
4. 不要通过本地编译绕过发布 wheel 问题。

### 14.3 `inspect` 返回配置错误或退出码 2

检查：

- `--scenario` 是否指向包含 `task.json` 的目录。
- `task.json` 声明的文件名、大小写和实际文件是否一致。
- JSON 是否为 UTF-8 且语法有效。
- 起终点和 GeoJSON 是否使用 `[longitude, latitude]`。
- 必需图层是否缺失或无法读取。

### 14.4 `plan` 返回无可行路径或退出码 3

不要删除 RFZ 或降低硬约束来伪造成功。应：

1. 用 `inspect` 检查范围和栅格尺寸。
2. 用 `grid` 输出 A/B/C 规划栅格。
3. 检查起终点是否位于场景范围内。
4. 检查 RFZ、建筑物高度和水平缓冲是否把可行空间完全断开。
5. 检查 DEM 是否正确朝向、NoData 和 CRS 是否正确。

### 14.5 macOS 报 `incompatible architecture`

这是 Python 和 wheel 架构不一致。Apple Silicon 上运行：

```bash
python3 -c 'import platform; print(platform.machine())'
```

结果为 `arm64` 时使用 arm64 wheel，结果为 `x86_64` 时使用 x86_64 wheel。推荐保持 Python、终端和 wheel 都为原生 arm64。

### 14.6 Web 页面没有在线底图或自动回退到离线

先确认 `.env` 位于运行命令的 `ale_aam_maptool` 目录，键名与 1.2 节一致，并在修改后重启服务。然后访问 `/v1/basemaps`：对应服务应显示 `available: true`，但响应中不应出现任何密钥。若服务可选但随后自动回退，通常是供应商侧来源限制、额度、网络/DNS 或样式权限问题；查看服务端通用错误状态即可，不要打印上游完整 URL。断网或正式 ALE 环境应主动选择 `offline`。

### 14.7 端口 8000 已占用

更换端口：

```bash
sh run.sh serve --scenario ./sample_scenario --host 127.0.0.1 --port 8765
```

然后访问 `http://127.0.0.1:8765/`。

### 14.8 `validate` 报缺少 final、CSV 或 Markdown

`plan-all` 只生成三条候选路线。必须按第 10 节自行计算风险、选择最终路线并完成应急方案，再执行完整目录校验。

### 14.9 路线在地图上落到错误国家或海域

首要检查坐标顺序。正确顺序始终是：

```text
[longitude, latitude]
```

香港示例通常约为 `[114.x, 22.x]`，不是 `[22.x, 114.x]`。

### 14.10 MSL 高度看起来比 AGL 高

这是正常的。MSL 包含当地地形高程，AGL 只表示离地高度。除海拔接近 0 的位置外，两者通常不同。

## 15. 维护者构建与验收

普通使用者不需要本节。

### 15.1 本地源码构建和测试

开发机需要 CMake 和对应平台 C++ 工具链：

```bash
python -m pip install .[test]
python -m pytest tests
```

正式发布应由 cibuildwheel CI 生成 wheel，不应要求最终用户执行源码构建。

### 15.2 单 wheel smoke

每个 wheel 应至少完成：

1. 安装到干净虚拟环境。
2. `doctor --json`。
3. `inspect` 示例场景。
4. `plan-all` 示例场景。
5. GeoJSON schema/硬约束校验。
6. 本地 `/v1/health` 检查。

### 15.3 跨平台一致性

在 Windows x64、Ubuntu x64、macOS Intel/arm64 使用同一微型场景、相同 Python 包版本和相同分辨率执行 `plan-all`。比较：

- A/B/C 坐标序列。
- 航点 AGL、MSL、速度和航向。
- 距离、时长和能耗。
- JSON/GeoJSON schema。

如果出现差异，优先排查浮点排序、原生 tie-break、CRS 轴顺序和输入栅格读取，不应以平台特例修改任务答案。

### 15.4 ALE 验收清单

- 三个任务均可被发现。
- `--dry-run` 通过。
- Ubuntu/Python 3.12 可从 wheelhouse 完全离线安装。
- `start()` 执行时 reference 不可见。
- 缺文件、坏 GeoJSON、RFZ 穿越、净空不足、风险表造假、最终路线不一致和缺少场景应急内容只降低对应分项。
- 人工核验 reference 得分为 1.0。
- 至少使用一个中等能力 agent 做三轮难度和泄漏检查。
- 发布前解决 RFZ 官方快照的 publication blocker。
- 不修改或覆盖 `ALE_v0.1`。

## 16. 许可证与数据来源

- 工具许可证见 `LICENSE`。
- jps3d 的 BSD-3-Clause 许可证见 `vendor/jps3d/LICENSE`。
- 第三方组件声明见 `THIRD_PARTY_NOTICES.md`。
- 每个 ALE 场景的数据来源、许可、获取日期、CRS、转换步骤和 SHA-256 见其 `input/source_manifest.json`。

发布任务前必须确认源数据许可允许当前分发方式，并固定所有远程来源，不能在 agent 运行期间动态下载或随机生成 GIS 数据。

## 17. 最短操作清单

如果只想确认工具可用，按以下顺序执行：

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
.\run.cmd doctor --json
.\run.cmd inspect --scenario .\sample_scenario --json
.\run.cmd plan-all --scenario .\sample_scenario --outdir .\output
.\run.cmd grid --scenario .\sample_scenario --route C --out .\output\grid_c.png
.\run.cmd serve --scenario .\sample_scenario --host 127.0.0.1 --port 8000
```

Ubuntu/macOS：

```bash
sh install.sh
sh run.sh doctor --json
sh run.sh inspect --scenario ./sample_scenario --json
sh run.sh plan-all --scenario ./sample_scenario --outdir ./output
sh run.sh grid --scenario ./sample_scenario --route C --out ./output/grid_c.png
sh run.sh serve --scenario ./sample_scenario --host 127.0.0.1 --port 8000
```

完成前三条候选路线后，再按第 10 节生成 `route_final.geojson`、`risk_assessment.csv` 和 `emergency_response_plan.md`，最后运行 `validate`。
