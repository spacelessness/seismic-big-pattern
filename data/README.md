# 数据目录与字段

## 存储约定

- `raw/`：有明确可再分发条款的上游原始文件，字节不变。
- `derived/`：可重建的轻量派生文件；具体筛选和字段变换记录在 `metadata/derivatives.json`。
- `licenses/`：上游许可原文、GEM/PB2002 说明与引用。
- `metadata/sources.lock.json`：上游仓库、固定 commit、原始文件路径、来源 URL、实际获取时间、字节大小、SHA256、存储状态。
- `metadata/catalog.json`：数据主题、机构、权威性类别、坐标系、状态与未取得原因。
- `metadata/known-issues.json`：已锁定原始文件的已知问题。
- `local/`：许可/申请待确认的本地数据，`.gitignore` 排除；首次收集时下载了 GMT 中国数据，但 **git clone 不包含它们**。
- `_cache/`：可以重新下载的城市完整源文件，不提交 Git。

## 断裂

### GEM 全球活动断裂

`raw/gem/gem_active_faults.geojson`：16,195 个 LineString；来源 GEM Foundation 的学术汇编数据库，不是中国官方活断层数据。全部上游属性保留，包括断层名称、来源、运动类型、滑动速率等，但**不同要素的字段可能不同、属性可能缺失**。

- 引用：Styron, R., & Pagani, M. (2020). The GEM Global Active Faults Database. *Earthquake Spectra*, 36(1_suppl), 160–180. DOI: `10.1177/8755293020944182`。
- 许可：CC BY-SA 4.0；本仓库的 GEM 筛选及 GMT 派生同样遵守该许可。
- 坐标：地理经纬度，按上游 GIS 数据的 WGS84 使用，未重投影；原 GeoJSON 未显式声明 CRS。
- `(most-likely,min,max)` 三元组保存为字符串，不得把缺失端点当作 0，不得把整个字段直接强制转换成 float。
- `derived/gem_faults_east_asia_bbox.geojson`：要素外包矩形与 **70–140°E、0–60°N** 相交的 2,343 条完整断裂。**未做几何裁剪**，所以范围可以超出窗口；也不是按中国国界筛选。
- 同名 `.gmt` 为经纬度线条；属性请读 GeoJSON。GMT 段头是零起始要素序号，不是上游永久断层 ID。

### CAFDv2023

见 `local/README.md`。不能把 GEM 东亚子集冒充 CAFD，也不能把旧版 CN-faults 的字段套用在 CAFDv2023 上。

## 板块与地块

`raw/pb2002/` 保留由 Hugo Ahlenius / Nordpil 转换、Peter Bird PB2002 模型派生的数据：

| 文件 | 要素数 | 类型 | 主要属性 |
|---|---:|---|---|
| `PB2002_plates.json` | 54 | Polygon / MultiPolygon | `Code`, `PlateName` |
| `PB2002_boundaries.json` | 241 | LineString | `Name`, `PlateA`, `PlateB`, `Source`, `Type` |
| `PB2002_orogens.json` | 13 | Polygon / MultiPolygon | `Name`, `Source` |

`derived/PB2002_boundaries.gmt` 可直接绘制边界线。`Type` 存在空值，不推断填补。保留上游日期变更线处理；没有重新构建拓扑。地理经纬度按 WGS84 使用，上游 GeoJSON 未显式声明 CRS。许可 ODC-By-1.0。引用 Bird (2003), DOI `10.1029/2001GC000252`，并署名 Hugo Ahlenius / Nordpil。

中国一、二级活动地块线在 `local/gmt-china/`（需自行恢复）。L1、推断 L1、L2 应分图层，不合并成一个“断层”类别，也不自动 polygonize。

## 城市坐标

Natural Earth 1:1000 万居民地数据的制图参考点，不是测绘控制点，也不保证覆盖所有地级市/县城。

| 文件前缀（在 derived/ 下） | 点数 | 内容 |
|---|---:|---|
| `cities_world.csv` | 7,342 | 全部源点、精选字段 |
| `cities_world_major.*` | 747 | `SCALERANK <= 3` 或源 `POP_MAX >= 1000000` |
| `cities_china.*` | 427 | 源代码 `CHN/HKG/MAC/TWN` 合并选取；不据此定义政治归属 |
| `cities_china_34_labels.*` | 34 | 31 个省区市省会/首府/直辖市及台北、香港、澳门；显式标注名单，不依靠源层级推断 |

CSV/GeoJSON 字段：

| 字段 | 含义 |
|---|---|
| `ne_id` | Natural Earth 标识；源版本内用于去重 |
| `name`, `name_zh` | 上游英文/中文名称，可能有旧拼写或繁体，不自动改写 |
| `longitude`, `latitude` | **取 geometry.coordinates**，单位度，WGS84 / CRS84、先经后纬 |
| `wikidata_id` | 原始关联 ID；未在线二次核查 |
| `source_adm0_a3`, `source_adm1_name` | 上游归属描述，保留原值，不视为中国官方行政区划 |
| `source_feature_class` | 上游制图分类，已知存在分类误差 |
| `source_scalerank` | 制图等级，小值优先显示 |
| `source_pop_max` | 上游制图用人口值，**不是当前年人口、不是风险暴露量** |
| `source_id` | 对应下载锁文件 ID |
| `label_admin_unit` | 仅 34 城市列表有；人工维护的标注区域名称，不覆盖上游字段 |

34 城市 GMT 文件：`longitude latitude 中文标签`，UTF-8，无人口列。不要直接使用旧 GMT5 脚本中的固定中文编码配置而不测试。

## 自然地理底图

`raw/natural_earth/`：1:5000 万（`50m` 指 **50 million 比例尺，不是 50 米分辨率**）。

- `ne_50m_coastline.geojson`：1,428 个要素。
- `ne_50m_lakes.geojson`：412 个要素。
- `ne_50m_rivers_lake_centerlines.geojson`：462 个要素，其中 1 个空几何。
- `derived/ne_50m_rivers_nonempty.geojson`：461 个非空要素，建议分析时使用。

坐标：源声明 `OGC:CRS84`，经纬度、度；Public Domain。适用于大区域背景，不适用于工程、水文精细分析或法定边界。本次没有入库 Natural Earth 政治边界图层。

## 坐标与距离

- GeoJSON 的坐标顺序是经度、纬度，不受 EPSG:4326 轴顺序描述影响。
- 中国官方 1:100 万原始资料采用 CGCS2000（EPSG:4490）；社区 CN-border 文件头声明 WGS84，但具体转换过程未完整说明。不得将两者标成完全相同的原始成果。
- CN-block 和当前 CN-faults 文件缺少明确基准声明，已记录为“经纬度、基准待核验”；不要只因坐标看起来合理就强行标为高精度 WGS84。
- km 距离、缓冲区和面积必须用大地测量或合适的投影计算，不能直接拿经纬度差当公里。
- 数据小数位数不等于真实精度。校验通过不代表通过地图审核，也不代表构造解释正确。
