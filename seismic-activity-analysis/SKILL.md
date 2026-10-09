---
name: seismic-activity-analysis
description: >
  综合地震活动性分析技能。目前已实现：
  1) EQT格式地震目录的读取（直接返回DataFrame，无需中间文件）；
  2) 写入（将DataFrame/CSV保存为标准EQT格式）；
  3) 震中分布图绘制（GMT5引擎，支持地理投影、地形底图、边界和断裂叠加）；
  4) 地震活动显著增强检测（网格化时空扫描，Benioff应变+频度双判据，自动估算完整性震级）；
  5) 地震活动显著平静检测（网格化时空扫描，D-T统计法+Z值法双方法，支持自动余震删除）。
  预留：地震空区识别、b值时间变化分析、能量释放加速分析等。
trigger:
  - 用户要求分析地震活动性、处理地震目录、转换EQT文件。
  - 用户提供 .eqt 文件路径或目录内容。
  - 用户提及"EQT格式""地震目录""读取""保存""转换为EQT""画图""震中分布""震中图""显著增强""活动增强""Benioff""应变释放""网格扫描"等关键词。
  - 用户提及"显著平静""地震平静""平静检测""D-T图""Z值""间隔时间""平静异常""quiescence"等关键词。
allowed-tools:
  - Bash
  - Python
  - Read
  - Write
  - Glob
---

# 地震活动性分析技能

## 功能概述

本技能提供一套模块化的地震活动性分析工具，**当前核心功能已完成**：

- **读取 EQT 文件**：解析中国地震台网中心常用的固定宽度 `.eqt` 格式，直接返回 Pandas DataFrame 用于后续分析。**无需**中间CSV文件。
- **写入 EQT 文件**：将符合格式要求的 DataFrame 或 CSV 文件导出为标准 EQT 格式（GBK 编码，固定字段宽度）。
- **绘制震中分布图**：使用 GMT5 引擎生成带有地理投影的震中分布图，支持地形底图、行政边界、活动断裂叠加，震中按震级分档显示不同符号大小。

所有操作均通过封装好的独立脚本进行，Claude 通过 `python -c` 直接调用 `read_eqt()` 函数获取 DataFrame 并完成分析。

---

## 当前可用功能

### 1. 读取 EQT 地震目录文件

**输入格式**：纯文本 `.eqt` 文件，每行一条事件，字段按固定宽度排列：

| 字段   | 起始列 | 结束列 | 说明               |
|--------|--------|--------|--------------------|
| 年     | 0      | 5      | 4 位数字           |
| 月     | 5      | 7      | 2 位数字           |
| 日     | 7      | 9      | 2 位数字           |
| 时     | 9      | 11     | 2 位数字           |
| 分     | 11     | 13     | 2 位数字           |
| 秒     | 13     | 15     | 2 位数字           |
| 纬度   | 15     | 21     | 浮点数，单位度     |
| 经度   | 21     | 28     | 浮点数，单位度     |
| 震级   | 28     | 32     | 浮点数             |
| 深度   | 32     | 39     | 浮点数，单位米     |
| 地名   | 39     | 行尾   | 中文地点描述       |

**返回**：Pandas DataFrame，包含以下列：
- `year, month, day, hour, minute, second`（整数）
- `latitude, longitude`（浮点，度）
- `magnitude`（浮点）
- `depth`（浮点，米）
- `location`（字符串，中文地名）

**实现脚本**：`scripts/read_eqt.py`

**推荐用法 —— 直接导入为 DataFrame，一步完成分析：**

```bash
# 读取 EQT → 筛选 M≥6 → 直接输出结果，无中间文件
python -c "
import sys; sys.path.insert(0, r'C:\Users\xxx\.claude\skills\seismic-activity-analysis\scripts')
from read_eqt import read_eqt
df = read_eqt(r'D:\path\to\catalog.eqt')
m6 = df[(df['year'] >= 2025) & (df['magnitude'] >= 6.0)]
print(m6[['year','month','day','latitude','longitude','magnitude','depth','location']].to_string())
"
```

**命令行用法（备用）：**

```bash
python read_eqt.py input.eqt              # 默认：打印摘要到 stdout，不产生文件
python read_eqt.py input.eqt --json       # 输出 JSON 到 stdout
python read_eqt.py input.eqt --summary    # 打印详细统计摘要
python read_eqt.py input.eqt -o out.csv   # 可选：保存为 CSV（仅在需要持久化时使用）
```

该脚本依赖 `pandas`，若未安装，Claude 应先执行 `pip install pandas`。

### 2. 保存 EQT 地震目录文件

**输入格式**：
接受 Python 的 DataFrame 类型数据或 CSV 文件（UTF‑8 或 GBK 编码），必须包含以下列：
year, month, day, hour, minute, second, latitude, longitude, magnitude, depth, location

**输出格式**：纯文本 `.eqt` 文件，每行一条事件，字段按固定宽度排列，按 GBK 编码：

| 字段   | 起始列 | 结束列 | 说明               |
|--------|--------|--------|--------------------|
| 年     | 0      | 5      | 4 位数字           |
| 月     | 5      | 7      | 2 位数字           |
| 日     | 7      | 9      | 2 位数字           |
| 时     | 9      | 11     | 2 位数字           |
| 分     | 11     | 13     | 2 位数字           |
| 秒     | 13     | 15     | 2 位数字           |
| 纬度   | 15     | 21     | 浮点数，单位度     |
| 经度   | 21     | 28     | 浮点数，单位度     |
| 震级   | 28     | 32     | 浮点数             |
| 深度   | 32     | 39     | 浮点数，单位米     |
| 地名   | 39     | 行尾   | 中文地点描述       |

**实现脚本**：`scripts/write_eqt.py`

该脚本依赖 `pandas` 和 `numpy`，若未安装，Claude 应先执行 `pip install pandas numpy`。

**用法：**

```bash
python scripts/write_eqt.py input.csv -o output.eqt    # CSV → EQT
```

### 3. 绘制震中分布图

**输入格式**：EQT 文件、CSV 文件、或含 `longitude/latitude/magnitude` 列的 DataFrame。
（也支持 `lon/lat/mag`、`lng/lat/m` 等别名，自动映射。）

**输出**：PNG 栅格图（600 dpi），附带 PS 矢量源文件。

**实现脚本**：
- `scripts/plot_epicenter.py` — Python 封装（推荐）  
- `scripts/plot_epicenter.bat` — GMT 批处理引擎（由 Python 脚本动态生成临时 bat 调用，无需手动使用）

**依赖**：GMT5（`gmt.exe` + `gawk.exe`）+ GIS 底图数据（`%GMT_DATADIR%` 环境变量指向）

**核心功能**：
- **地理投影**：默认为墨卡托投影（M6i），可自定义 GMT 投影字符串
- **行政边界**：自动叠加省界、市界、县界（需 `%GMT_DATADIR%` 下有对应 `.gmt` 文件）
- **城市标注**：省会（大圆 + 大字）、地级市（中圆 + 中字）、县城（小点 + 小字）
- **活动断裂**：可选叠加断裂线（红色），默认开启
- **地形底图**：可选渲染灰度地形阴影（耗时长，需要 `earth_relief_15s.grd`）
- **震级分档**：自动按震级分 6 档，不同符号大小显示：

| 震级范围 | 符号直径 |
|----------|:--------:|
| M ≥ 7.0 | 9p |
| M6.0–6.9 | 7p |
| M5.0–5.9 | 6p |
| M4.0–4.9 | 5p |
| M3.0–3.9 | 4p |
| M2.0–2.9 | 3p |

- **图例**：自动生成，含震级符号说明（+ 断裂图例）
- **自动区域**：不指定 `region` 时自动从数据范围推算（含 0.5° 边距）

**推荐用法 —— 导入调用：**

```python
from plot_epicenter import plot_epicenter

# 从 EQT 文件绘制，自动区域
plot_epicenter('catalog.eqt', 'output.png', title='地震震中分布图', mag_min=4.0)

# 指定区域 + 震级范围
plot_epicenter('data.csv', 'map.png', region=(100, 125, 35, 55),
               title='某区域地震活动', mag_min=5.0)

# 从 DataFrame 绘制
plot_epicenter(df, 'output.png', show_faults=False)
```

**命令行用法：**

```bash
# 基本用法
python plot_epicenter.py input.eqt -o output.png -t "震中分布图"

# 指定区域和震级
python plot_epicenter.py input.csv -o map.png -r 100/120/35/45 --mag-min 5.0

# 开启地形底图
python plot_epicenter.py input.eqt -o map.png --topo

# 不显示断裂
python plot_epicenter.py input.eqt -o map.png --no-faults
```

**参数说明：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `input_data` | str / Path / DataFrame | (必填) | 输入数据 |
| `output_path` | str / Path | (必填) | 输出 PNG 路径 |
| `region` | tuple (w,e,s,n) / None | None | 绘图区域，None 则自动 |
| `title` | str | `'震中分布图'` | 地图标题 |
| `mag_min` | float / None | None | 震级下限 |
| `mag_max` | float / None | None | 震级上限 |
| `show_topo` | bool | False | 是否渲染地形底图 |
| `show_faults` | bool | True | 是否叠加活动断裂 |
| `projection` | str | `'M6i'` | GMT 投影字符串 |
| `gis_dir` | str / None | None | GIS 数据目录，默认 `%GMT_DATADIR%` |

该脚本依赖 `pandas`，若未安装，Claude 应先执行 `pip install pandas`。

### 4. 地震活动显著增强检测

基于《测震分析预测技术方法工作手册》第5章定义，对地震目录进行**网格化时空扫描**，自动识别满足判据的地震活动显著增强区域。

**判据来源**：文档 5.3 节"识别方法"

**核心判据**：

| # | 条件 | 量化标准 |
|:--|:--|:--|
| ① | 应变释放加速 | 年 Benioff 应变释放量 ≥ 前 3 年平均的 **2 倍** |
| ② | 频度同步上升 | 年地震频度 ≥ 前 3 年平均的 **2 倍** |
| ③ | 加速持续 | 上升时间至少持续 **1 年**以上 |
| ④ | 曲线形态 | 应变释放曲线呈上翘弧形（加速特征） |

**Benioff 应变公式**：
```
E = 10^(4.8 + 1.5×M)  Joule
√E = 10^(2.4 + 0.75×M)  J^(1/2)
```

**算法**：
1. 自动估算目录完整性震级 Mc（MAXC 最大曲率法）
2. 按指定网格大小（默认 1°×1°）划分空间
3. 每网格 + 每滑动窗口（6月/12月）计算：
   - 窗口内年化 Benioff 应变释放量
   - 窗口内年化地震频度
   - 前 3 年基线平均值
4. 双判据同时 ≥ 2× 且持续 ≥ 12 月 → 标记为增强
5. 相邻网格重叠增强自动合并去重

**实现脚本**：`scripts/enhancement_detector.py`

**依赖**：`pandas`, `numpy`, `python-dateutil`

**推荐用法 —— 导入调用：**

```python
from enhancement_detector import detect_enhancement, benioff_strain

# 自动网格扫描
result = detect_enhancement('catalog.eqt', grid_size=1.0, windows=(6, 12))

# 指定震级下限 + 保存结果
result = detect_enhancement('catalog.csv', mc=2.0, 
                            grid_size=1.5, windows=(12,),
                            output_path='enhancement_results.csv')

# 使用 DataFrame
result = detect_enhancement(df, grid_size=2.0)
```

**命令行用法：**

```bash
# 基本用法
python enhancement_detector.py input.eqt -o results.csv

# 指定网格大小和窗口
python enhancement_detector.py input.eqt -g 1.5 --windows 12 -o results.csv

# 手动指定完整性震级
python enhancement_detector.py input.eqt --mc 2.0 -g 1.0
```

**参数说明：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `input_data` | str / Path / DataFrame | (必填) | 输入数据 |
| `grid_size` | float | `1.0` | 网格大小（度） |
| `windows` | tuple | `(6, 12)` | 滑动窗口长度（月） |
| `mc` | float / None | None | 完整性震级，None 则自动估算 |
| `min_events` | int | `10` | 网格最少事件数 |
| `min_duration_months` | int | `12` | 增强最少持续月数 |
| `output_path` | str / None | None | 结果 CSV 输出路径（可选） |

**返回**：DataFrame，每行一个增强时段，列包含：
- `grid_lat/lon` — 网格中心经纬度
- `grid_w/e/s/n` — 网格四至边界
- `enhance_start/end` — 增强起止时间
- `duration_months` — 持续月数
- `strain_ratio` — 应变释放量/基线比
- `count_ratio` — 频度/基线比
- `n_events_window` — 窗口内事件数
- `max_magnitude` — 窗口内最大震级
- `total_strain` — 总 Benioff 应变
- `window_months` — 分析窗口长度
- `mc_used` — 使用的完整性震级

### 5. 地震活动显著平静检测

基于《测震分析预测技术方法工作手册》第7章定义，对地震目录进行**网格化时空扫描**，自动识别满足判据的地震活动显著平静区域。

**判据来源**：文档 7.3 节"识别方法"

**定义**：在区域地震正常活动或显著增强背景下，局部出现的地震活动水平明显降低甚至无震的现象。

**核心判据**：

| # | 条件 | 量化标准 |
|:--|:--|:--|
| ① | 间隔时间异常 | 当前地震间隔时间 ≥ 历史均值 μ + k·σ（默认 k=2） |
| ② | 统计显著性 | 间隔时间超过 95% 分位值交叉验证 |
| ③ | Z 值检验 | Z = (R₁−R₂)/√(R₁/T₁+R₂/T₂) ≥ 阈值（默认 2.0） |

**两种检测方法**：

| 方法 | 原理 | 来源 |
|:--|:--|:--|
| **D-T 统计法** | 计算历史地震间隔时间均值 μ 和标准差 σ，以 μ+2σ 为异常阈值 | 文档 7.3.1 节 |
| **Z 值法** | 基于累计频度变化率的泊松假设 Z 检验，Z>0 表示活动减弱 | 文档 7.3.2 节 |

**算法流程**：
1. **余震删除**：Gardner-Knopoff 时空窗法自动去除余震
2. **完整性震级估算**：MAXC 最大曲率法自动估算 Mc
3. **网格划分**：按指定网格大小（默认 1°×1°）划分空间
4. **D-T 扫描**：每网格计算事件间隔 μ、σ，找超过 μ+2σ 的异常间隙
5. **Z 值扫描**：每网格滑动窗口计算 Z 值时间序列，找 Z≥阈值的连续时段
6. **合并去重**：相邻网格重叠平静时段自动合并

**Gardner-Knopoff 余震删除**：
- 空间窗半径（km）：R = 10^(0.1238·M + 0.983)
- 时间窗（天）：
  - M ≥ 6.5：T = 10^(0.032·M + 2.7389)
  - M < 6.5：T = 10^(0.5409·M − 0.547)

**实现脚本**：`scripts/quiescence_detector.py`

**依赖**：`pandas`, `numpy`, `python-dateutil`

**推荐用法 —— 导入调用：**

```python
from quiescence_detector import detect_quiescence

# 基本用法：自动网格扫描（D-T + Z值）
result = detect_quiescence('catalog.eqt', grid_size=1.0)

# 只用 D-T 法
result = detect_quiescence('catalog.eqt', method='dt', sigma_mult=2.0)

# 只用 Z 值法
result = detect_quiescence('catalog.eqt', method='zvalue', z_window=365, z_threshold=2.0)

# 保留余震 + 指定震级下限 + 保存结果
result = detect_quiescence('catalog.eqt', do_remove_aftershocks=False,
                            mag_threshold=4.0, output_path='quiescence_results.csv')
```

**命令行用法：**

```bash
# 基本用法
python quiescence_detector.py input.eqt -o results.csv

# 指定参数
python quiescence_detector.py input.eqt -g 1.5 --mc 4.0 --method dt -o results.csv

# Z值法为主（更大窗口）
python quiescence_detector.py input.eqt --method zvalue --z-window 365 --z-step 60
```

**参数说明：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `input_data` | str / Path / DataFrame | (必填) | 输入数据 (.eqt / .csv / DataFrame) |
| `grid_size` | float | `1.0` | 网格大小（度） |
| `mag_threshold` | float / None | None | 震级下限，None 则自动估算 Mc |
| `method` | str | `'both'` | `'dt'` / `'zvalue'` / `'both'` |
| `do_remove_aftershocks` | bool | `True` | 是否先删除余震 |
| `sigma_mult` | float | `2.0` | D-T σ 倍乘系数（μ + k·σ） |
| `min_gap_days` | float | `30` | D-T 最短平静时长（天） |
| `z_window` | int | `180` | Z值法滑动窗口（天） |
| `z_step` | int | `30` | Z值法时间步长（天） |
| `z_threshold` | float | `2.0` | Z值显著性阈值 |
| `min_duration_days` | float | `90` | Z值法平静最短持续天数 |
| `min_events` | int | `20` | 网格最少事件数 |
| `output_path` | str / None | None | 结果 CSV 输出路径（可选） |

**返回**：DataFrame，每行一个平静时段，列包含：

| 列 | 说明 |
|:--|:--|
| `grid_lat`, `grid_lon` | 网格中心经纬度 |
| `grid_w`, `grid_e`, `grid_s`, `grid_n` | 网格四至边界 |
| `quiescence_start`, `quiescence_end` | 平静起止时间 |
| `duration_days` | 持续天数 |
| `method` | 检测方法（D-T / Z-value / D-T+Z-value） |
| `threshold_days` | D-T 法的异常阈值（天） |
| `mean_gap_days`, `std_gap_days` | 间隔均值、标准差 |
| `p95_days` | 间隔 95% 分位值 |
| `z_peak` | Z 值峰值 |
| `last_event_mag` | 平静前最后一个事件的震级 |
| `next_event_mag` | 打破平静的事件的震级（None 表示尚未打破） |
| `ongoing` | 平静是否持续到目录末尾 |
| `n_events_grid` | 网格内总事件数 |
| `mc_used` | 使用的完整性震级 |

**判据解读**：
- **D-T+Z-value**：两种方法均检测到 → 最高置信度
- **D-T only**：仅间隔时间超过 μ+2σ → 统计显著，需结合 Z 值验证
- **Z-value only**：仅 Z 值超过阈值 → 活动率下降显著，但间隔仍在正常范围

---

## 可用脚本

| 脚本 | 用途 | 说明 |
|------|------|------|
| `scripts/read_eqt.py` | 读取 EQT | **推荐作为模块导入**：`from read_eqt import read_eqt; df = read_eqt(path)` |
| `scripts/write_eqt.py` | 写入 EQT | `python write_eqt.py input.csv -o output.eqt` |
| `scripts/plot_epicenter.py` | 震中分布图 | `from plot_epicenter import plot_epicenter; plot_epicenter(input, output)` |
| `scripts/plot_epicenter.bat` | GMT 绘图引擎 | 由 Python 自动生成临时脚本调用，一般无需手动使用 |
| `scripts/enhancement_detector.py` | 活动增强检测 | `from enhancement_detector import detect_enhancement; detect_enhancement(input)` |
| `scripts/quiescence_detector.py` | 活动平静检测 | `from quiescence_detector import detect_quiescence; detect_quiescence(input)` |
