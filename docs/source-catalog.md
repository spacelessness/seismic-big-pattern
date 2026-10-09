# 重点数据来源目录与待办

状态截至 **2026-10-09**。机器可读主题目录见 `data/metadata/catalog.json`；文件级可复现 URL/commit/SHA256 见 `sources.lock.json`。本页的“仅登记”不能计入已收集的数据量。

## 已实际获取

| 数据 | 发布/维护主体与权威性 | 获取状态 | 适用用途 |
|---|---|---|---|
| [GEM GAF](https://github.com/GEMScienceTools/gem-global-active-faults) | GEM Foundation，同行评议学术汇编 | **已入库** | 全球及中国周边区域断裂背景、运动学属性 |
| [PB2002](https://github.com/fraxen/tectonicplates) | Peter Bird 学术模型；Nordpil 社区 GIS 转换 | **已入库** | 全球板块、边界、造山带；不是中国块体层级 |
| [Natural Earth](https://github.com/nvkelso/natural-earth-vector) | 成熟公共领域制图项目，非中国官方测绘数据 | **已入库** | 城市坐标、海岸线、河流、湖泊 |
| [CN-faults](https://docs.gmt-china.org/latest/dataset/CN-faults/) | 中国活断层数据库 CAFDv2023 的 GMT 社区转换版 | **已下载、本地保留** | 中国断裂背景；需核验数据许可与基准 |
| [CN-block](https://docs.gmt-china.org/latest/dataset/CN-block/) | 中国活动地块论文图件的社区数字化 | **已下载、本地保留** | 一级、一级推断、二级地块边界线 |
| [CN-border](https://docs.gmt-china.org/latest/dataset/CN-border/) | 官方基础地理数据来源的社区派生 | **已下载、本地保留** | 科研参考；不替代官方原始数据和地图审核 |
| [USGS ComCat](https://earthquake.usgs.gov/fdsnws/event/1/) 区域快照 | USGS 官方地震目录接口 | **已入库**：125,721 事件（1901–2026），无震级下限 | 中国及周边长时段背景；震级未均一化；非全国小震完备目录 |
| [青藏高原 1970–2022](https://zenodo.org/records/14525785) | 研究者整理（说明来源为 CENC），CC BY 4.0 | **已入库**：27,050 条，UTC+8 表头已换算 | M3+ 为主；258 条深度缺测；非官方直发 |
| [四川及邻区 2013–2018](https://zenodo.org/records/5602183) | 研究者整理，CC BY 4.0 | **已入库**：199,292 条 | 时区/震级类型未说明；止于 2018-05-26 |
| [四川 AI 目录 2019–2020 v2](https://zenodo.org/records/21787957) | 研究者 AI 检出目录，CC BY 4.0 | **已入库**：380,886 条 | 含负震级；时区未说明；禁与常规目录拼接 |

上游权威性分级并不是精度保证；尤其 PB2002 和 CN-block 是历史模型，不能描述所有后续发现。四个地震目录分开存放、互不合并，详见 [已入库地震目录](earthquake-catalogs.md)。

## 优先补齐：官方边界与地震学数据

| 优先级 | 来源与入口 | 建议获取内容 | 状态/限制 |
|---|---|---|---|
| P0 | [全国基础地理信息数据](https://www.webmap.cn/commres.do?method=result100W)、[天地图数据资源](https://cloudcenter.tianditu.gov.cn/dataSource) | 1:100 万境界与政区、居民地/地名层，保留 CGCS2000 与版本 | **未取得官方包**；原平台页面本次遇 WAF；应按当前平台申请 |
| P0 | [自然资源部标准地图](https://bzdt.ch.mnr.gov.cn/) | 与发表图范围一致的官方标准底图及审图信息 | **仅登记**；本次页面未成功获取 |
| P0 | [国家地震科学数据中心](https://data.earthquake.cn/) / [中国地震台网](https://news.ceic.ac.cn/) | 中国正式地震目录、历史地震目录、震源机制 | **官方页面已核查，未取得全量导出**；申请清单见 [中国官方目录说明](china-earthquake-catalog-requests.md) |
| P1 | [USGS ComCat FDSN](https://earthquake.usgs.gov/fdsnws/event/1/) | 区域/全球事件 CSV 或 GeoJSON，保留 id、magType、误差、更新时间 | **区域快照已入库**；后续更新用 `scripts/collect_usgs_catalog.py` 另建快照目录 |
| P1 | [ISC-GEM](https://www.isc.ac.uk/iscgem/) | 长时段大震分析的均一化目录 | **仅登记候选入口**；未核查当前具体版本/条款，不能与 ComCat 无条件拼接 |
| P1 | [Global CMT](https://www.globalcmt.org/CMTfiles.html) | NDK 震源机制、矩张量 | **仅登记**；保留矩心与震源位置区别、quick/正式状态 |
| P1 | [中国地震台网中心 CMT](https://data.earthquake.cn/datashare/report.shtml?PAGEID=earthquake_dzzyjz) | 中国大陆中强震及全球强震矩张量解 | **仅登记**；DOI `10.12080/nedc.11.ds.2022.0005` |

官方 1:100 万产品参数见 [1](https://www.webmap.cn/commres.do?method=result100W)，迁移提示见 [3](https://www.webmap.cn/commres.do?method=dataDownload)。中国台网 CMT 产品说明见 [2](https://data.earthquake.cn/datashare/report.shtml?PAGEID=earthquake_dzzyjz)。Global CMT 的 NDK 与月度目录入口见 [1](https://www.globalcmt.org/CMTfiles.html)。

## 轻量且有价值的扩展（均未把实体文件入库）

| 优先级 | 数据 | 官方/机构入口 | 建议取用方式与限制 |
|---|---|---|---|
| P1 | World Stress Map 2025 地应力 | [WSM](https://www.world-stress-map.org/)、[DOI 10.5880/WSM.2025.001](https://doi.org/10.5880/WSM.2025.001) | CSV 按区域/质量筛选；保留质量等级、深度、应力类型、来源；不要只画方向而忽略等级 |
| P1 | GNSS 台站速度 | [UNR Nevada Geodetic Laboratory](https://geodesy.unr.edu/)、[MIDAS IGS20](https://geodesy.unr.edu/gps_timeseries/IGS20/midas/midas.IGS.txt) | 先取区域速度表而非全部时间序列；参考框架、历元、速度单位、不确定度需保留 |
| P1 | 形变/应变率 | [NGL GSRM](https://geodesy.unr.edu/gsrm.php) | 区域稀疏网格/速度场优先；不得将长期应变率直接当作短期概率 |
| P2 | GMT 地形起伏 | [GMT 远程数据](https://docs.gmt-china.org/latest/dataset/remote-dataset/) | 全国大形势优先 `@earth_relief_10m` 或 `05m`；仅按区域取用，不提交全球 15 秒栅格 |
| P2 | GSHHG 海岸线 | [GMT GSHHG](https://github.com/GenericMappingTools/gshhg-gmt) | 优先 GMT 自带 low/intermediate 数据；与本次 NE 底图是替代选项，不混为同一版本 |
| P2 | 俯冲带三维几何 Slab2 | [USGS 官方仓库](https://github.com/usgs/slab2) | **仅登记候选，未下载核验**；环太平洋深震分析时按区域取模型和误差，不整库搬运 |
| P2 | 中国强震动参数 | [国家地震科学数据中心](https://data.earthquake.cn/datashare/report.shtml?PAGEID=ground_motion_list) | 事件相关 PGA/PGV/烈度点数据，通常比全波形轻；主要用于影响分析而非地震活动性统计 |
| P3 | 更密集地名点 | [GeoNames 下载](https://download.geonames.org/export/dump/) | **仅登记候选**；可选 cities15000，先核验 CC BY 条款、人口现势性和行政归属 |

WSM 官方首页已核查，2025 版 100,842 条记录；本次未获取 CSV。NGL 官方首页已核查 IGS20 MIDAS 链接和引用要求，未取速度表。强震动产品的字段和用途依据 [3](https://data.earthquake.cn/datashare/report.shtml?PAGEID=ground_motion_list)。

## 暂不收集的重型资料

连续波形、全分辨率全球 DEM、全量遥感影像、全部 GNSS 时间序列、InSAR 栈和高分辨率道路建筑物，不是第一阶段大形势底图所必需，也不适合直接塞进 Git。若后续专题确有必要，按区域/时段获取，使用外部存储或专门数据发布机制。

## 引用与检查纪律

1. 优先原发布机构、DOI 与机构维护仓库，不采用无版本说明的网盘拼包。
2. 文件获取日期和数据观测/模型年代分开记录；本次获取不意味着数据都是 2026 年最新成果。
3. 社区转换文件保留与官方原成果之间的来源链和处理缺口。
4. 目录有链接不等于数据已下载；权限不明也不能自动归为开放数据。
5. “DMT 中文社区”未确认准确站点；详见中国数据说明，不将其臆定为已核查来源。
