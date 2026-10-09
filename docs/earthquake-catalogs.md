# 已入库地震目录：内容、字段与使用边界

整理日期 **2026-10-09**。需求是**中国及周边、尽可能长的时间、所有公开可获得的震级，不预设完备性**。区域工作框为 **70–140°E、0–60°N**（含大量邻国与海域，**不是中国国界**）。

## 1. 已入库一览

| 目录 | 时间（实际数据） | 记录数 | 最小震级 | 时区 | 位置 |
|---|---|---:|---|---|---|
| USGS ComCat 快照 `east_asia_2026-10-09` | 1901-06-24 至 2026-10-08（UTC） | 125,721 事件，其中地震 125,502、M<5 地震 98,087、缺震级 8,089 | 0.0（含缺测） | UTC | `data/catalogs/usgs/east_asia_2026-10-09/` |
| 青藏高原 1970–2022（CENC 来源，研究者整理） | 1970-01-05 至 2022-12-31 | 27,050 | 2.4 | 源表头 UTC+8，已换算 UTC | `data/catalogs/zenodo/qinghai_tibet_1970_2022/` |
| 四川及邻区 2013–2018（研究目录） | 2013-01-01 至 2018-05-26 | 199,292 | 0.0 | **未说明，不换算** | `data/catalogs/zenodo/sichuan_2013_2018/` |
| 四川 AI 目录 2019–2020 v2 | 2019-01-01 至 2020-12-31 | 380,886 | −1.7（含负震级） | **未说明，不换算** | `data/catalogs/zenodo/sichuan_ai_2019_2020_v2/` |

以上数字是**本仓库校验后的实际记录数**，不是发布方宣传数字。四个目录**分开存放、互不合并**：同一地震可能在多个目录中出现，**不跨来源自动去重**。

**仍缺**：全国统一编目正式目录全量导出、CSN 1970–2017 全量导出。申请入口与需求文本见 [中国官方长时段中小地震目录](china-earthquake-catalog-requests.md)。四个已入库目录都**不是“全国完整官方小震目录”**。

## 2. USGS ComCat 快照

- 查询条件：`70–140°E、0–60°N`，`starttime=1000-01-01T00:00:00Z`，`endtime` 为 2026-10-09（不含，即含至 2026-10-08 末毫秒）；**无震级下限、无事件类型筛选**，返回 preferred origin/magnitude。
- 起始 1000 年只是 API 下界，**不表示 1000 年以来小震齐全**；实际首条为 1901 年 M7.2 琉球群岛地震。
- 采集时按 12,000 条上限自动二分时段，共 18 个不重叠毫秒区间（其中 3 个空区间），每段下载前后各做一次 `count` 核对；根区间下载前后总数与去重后唯一事件数三者一致（125,721）才允许发布。
- `raw/part-*.csv.gz` 保存原始 CSV 响应的无损 gzip；`events.csv.gz` 为全部事件的规范化列，`earthquakes_m_lt5.csv.gz` 仅含 `event_type=earthquake` 且震级 <5 的 98,087 条，`annual_counts.csv` 为按年/事件类型/震级类型分档计数。
- 震级类型混杂（`mb` 占多数，另有 `mw/mwc/mww/mwb/mwr/ms/ml/md` 等及缺测），**未均一化**；非地震事件（核爆 212 条等）保留在 `events.csv.gz` 中。
- 贡献机构保留在每条记录的 `network/origin_source/magnitude_source` 中；USGS 自产信息为美国公有领域，但第三方贡献需保留其署名与权利，不做整体重新许可。
- 采集脚本：`scripts/collect_usgs_catalog.py`（标准库，无需账号，无震级/类型过滤参数）。

主要字段（`events.csv.gz`）：`event_id, origin_time_utc, longitude, latitude, depth_km, magnitude, magnitude_type, event_type, review_status, updated_utc, network, origin_source, magnitude_source, horizontal_error_km, depth_error_km, magnitude_error, nst, gap_deg, dmin_deg, rms_s, mag_nst, place, source_catalog, source_chunk`。空字符串表示缺测，**不是零**。

## 3. 三个 CC BY 4.0 区域目录

全部按 Zenodo 记录号/文件名/MD5 锁定，下载时复核 `open + cc-by-4.0`，原文无损保存（文本 gzip、表格原样），再生成统一列的 `catalog.csv.gz`。**不做空间/震级截断、不去重、不去丛集、不均一化**。`source_record_id` 是“记录号+源行号”的本地引用，**不是全球事件 ID**。

### 青藏高原 1970–2022（Zenodo 14525785 v2）

- 来源说明为 CENC，范围 20–45°N、75–110°E；实际数据 bbox 恰为该范围。
- 工作表头明确 `Time (UTC+8)`，据此换算 `origin_time_utc`（如汶川主震源 14:27:59 → UTC 06:27:59），原始 Excel 序列值保留在 `source_time_serial`。
- 震级以 Ms/mL 为主（大小写按源保留：`ML` 与 `mL` 是不同的源写法，不合并），最小 2.4；**基本是 M3+ 目录，只有 36 条 2–3 级**，不能当小震完备目录用。
- 深度 258 条为 `-`，原样保留并计为缺测（`depth_value_missing=258`），**不是 0 km**。
- 注意源文件为 `.xlsx`，`catalog.csv.gz` 是按该锁定版本写的专用解析结果，不是通用 Excel 导入器。

### 四川及邻区 2013–2018（Zenodo 5602183 v2）

- 文本 10 列：`年 月 日 时 分 秒 纬度 经度 深度 震级`；实际共 199,292 行，止于 2018-05-26（**不是完整 2018 全年**）。
- 源未说明时区、震级类型、深度单位与坐标基准：`origin_time_utc` 为空，`magnitude_type` 为空，`depth_unit=unspecified`，**不得擅自标注 UTC 或 ML**。
- 实际经纬度范围 95–110°E、16–35°N，超出四川省界使用时注意。
- 震级 0–2 占多数，另有 1,344 条 0 级（按源保留，不删除、不改写）。

### 四川 AI 目录 2019–2020 v2（Zenodo 21787957）

- 深度学习拾震 + 三维速度模型重定位的研究目录，380,886 条；v2 修补了 v1 部分缺失时段，**以 v2 为准**。
- 源数据集描述称震级为 ML，`magnitude_type=ML`；但**时区未说明**，`origin_time_utc` 为空。源示例日期与已知地震（如 2019-06-17 长宁 6.1 级为 22:55）的时间一致性需使用者自行核对后再决定如何使用时间列。
- 含 77,665 条负震级与 26,954 条零级（最小 −1.7），按源保留；质控列（`rms/err/nrec`）保留在 `*_source` 字段中。
- 这是**算法检出目录**，检出能力与常规台网不同；2019–2020 年数量远高于常规目录是方法差异，**不能直接与常规目录拼接做活动性趋势**，也不能视为官方正式编目。

区域派生统一列：`source_record_id, source_row_number, origin_time_source, origin_time_utc, timezone_status, source_time_serial, longitude, latitude, depth_value, depth_unit, magnitude, magnitude_type, rms_source, err_ns_source, err_ew_source, err_depth_source, nrec_source, location, source_id`。构建脚本 `scripts/build_regional_catalogs.py`；校验 `python scripts/build_regional_catalogs.py --verify`。

## 4. 引用

- USGS ComCat：`Credit: U.S. Geological Survey`，并保留各事件贡献机构；权利说明 <https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits>。
- Yang, Ting et al. (2026). AI-derived earthquake catalog for Sichuan Province, China (v2). Zenodo. DOI `10.5281/zenodo.21787957`. CC BY 4.0.
- Sun, Mengyao (2021). Sichuan GNSS data and earthquake catalog (v2). Zenodo. DOI `10.5281/zenodo.5602183`. CC BY 4.0.（本仓库仅收录其中地震目录文本，未收录 GNSS 包。）
- Hu, Xiaokang (2024). The Qinghai-Tibet Plateau earthquake catalog (1970–2022) (v2). Zenodo. DOI `10.5281/zenodo.14525785`. CC BY 4.0.（来源说明为 CENC 整理子集。）
- 若取得中国正式/历史目录，按 `docs/china-earthquake-catalog-requests.md` 的要求使用官方建议引用与致谢，**不把研究者整理版冒充官方直接发布**。

## 5. 使用前必读

1. 时区：只有 ComCat（UTC）与青藏高原表（UTC+8 表头）有可用 UTC；另两个区域目录的 `origin_time_source` **不得直接当 UTC** 与其他目录拼时间序列。
2. 震级：Ms/mb/ML/Mw 不互换；`ML` 与 `mL` 不合并；负震级、零级、缺测、`-` 各有含义，不得填零。
3. 重复：同一地震可同时出现在 ComCat 与区域目录中；AI 目录与常规目录的事件无对应 ID，**禁止按“时间接近”自动去重/匹配**。
4. 完备性：年度数量跳变首先怀疑台网/算法/收录口径变化（如青藏高原 2008 年 2,732 条含汶川序列、四川 AI 目录 2019–2020 年均约 19 万条），**不得直接解读为活动增强或减弱**。
5. 深度：ComCat 深度单位 km；青藏高原表深度单位 km；另两个区域目录深度单位未说明，且含大量 5/10/20 等取整值，**不得做高精度深部分布解释**。
6. 本集合不提供地震预测，不替代工程设防与应急决策依据。
