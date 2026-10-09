# 地震大形势分析：公开数据底座

本仓库已有 EQT 地震目录与活动性分析脚本。本次新增的是**可溯源、可校验、尽量轻量的基础数据集**，整理日期 **2026-10-09**。不修改原有地震目录，不将底图或构造模型当作地震预测结论。

## 收集结果与明确缺口

| 类别 | 结果 | 状态 |
|---|---|---|
| 全球活动断裂 | GEM GAF：16,195 条线要素，保留全部上游属性；另有东亚分析窗口 2,343 条要素 | **数据已入库** |
| 全球构造板块 | PB2002：54 个板块面、241 条边界线、13 个造山带面 | **数据已入库** |
| 中国及周边活断层 | GMT 中文社区 CAFDv2023 转换版，10,534 个 GMT 段 | **已下载校验；本地保留，未再分发** |
| 中国一级/二级活动地块 | CN-block-L1 / L1-deduced / L2，分别 8 / 10 / 25 个线段 | **已下载校验；本地保留，未再分发** |
| 中国行政边界 | 找到自然资源部授权的 1:100 万公众版数据及标准地图官方入口；GMT 社区国界省界也已本地下载 | **官方原始数据未取得；社区版不是官方原始成果** |
| 城市经纬度 | Natural Earth：全球 7,342 点；重要城市筛选 747 点；中国相关城市 427 点；34 个省级区域城市标注点 | **CSV / GeoJSON / GMT 数据已入库** |
| 轻量级自然地理底图 | Natural Earth 1:5000 万海岸线、河流、湖泊；河流另提供去空几何版 | **数据已入库** |
| 中国及周边地震目录 | USGS ComCat 快照 125,721 事件；青藏高原 27,050 条；四川 2013–2018 年 199,292 条；四川 AI 2019–2020 年 380,886 条 | **数据已入库；全国正式目录仍待申请** |
| 震源机制、地应力、GNSS、地形、俯冲带等 | 官方或学术机构入口、引用及获取建议 | **仅来源登记，未下载数据** |

**不是“所有数据已收齐”。** 中国官方边界需在官方平台获取并核实使用条款；GMT 中文数据仓库未发现统一的明确再分发许可证，因此此仓库提交其固定版本索引、SHA256 和下载工具，而不擅自给这些数据套用开源许可证。具体见 [中国数据与官方边界获取说明](docs/china-official-data.md)。

> 8/10/25 是文件里的**线段数量，不是地块个数**。CN-block 是论文图件矢量化的边界线，并非可直接用于点落区统计的闭合地块面。PB2002 全球板块也不等于中国一级/二级活动地块。

## 从这里开始

- [数据目录、适用范围、坐标系与字段](data/README.md)
- [已入库地震目录：内容、字段与使用边界](docs/earthquake-catalogs.md)
- [中国官方长时段中小地震目录申请清单](docs/china-earthquake-catalog-requests.md)
- [所有重点来源与待补充清单](docs/source-catalog.md)
- [中国官方边界、CAFD 与活动地块](docs/china-official-data.md)
- [数据许可与署名](data/DATA_LICENSES.md)
- [已知质量问题与使用限制](docs/data-quality.md)
- [补充数据获取配方](docs/acquisition-recipes.md)
- [原有分析技能](seismic-activity-analysis/SKILL.md)

## 直接使用

QGIS 可以打开 `data/raw/**/*.geojson`、`data/raw/pb2002/*.json`、`data/derived/*.geojson`。
CSV 的坐标列为 **`longitude, latitude`**（度），UTF-8 编码；不要与百度/高德偏移坐标直接混用。

```python
# 标准库读取城市点，不需要 GIS 依赖
import csv
with open('data/derived/cities_china_34_labels.csv', encoding='utf-8', newline='') as f:
    cities = list(csv.DictReader(f))
print(cities[0]['name_zh'], cities[0]['longitude'], cities[0]['latitude'])
```

GMT 6 区域叠加示例：[examples/plot_context_gmt6.sh](examples/plot_context_gmt6.sh)。示例不绘制行政国界，避免把国际底图误当成中国官方边界；并非已审定可发表的地图。

## 复现与校验

新增工具只依赖 **Python 3.10+ 标准库**；下载需要 GitHub CLI `gh` 和相应网络连接，GIS 查看与 GMT 出图是可选的。

```bash
# 克隆后即可离线校验已入库的数据
python scripts/validate_public_data.py
python scripts/validate_earthquake_catalogs.py --all
python -m unittest discover -s tests -v

# 补齐/校验固定版本原始文件；已有正确文件不会重新下载
python scripts/fetch_public_data.py --include-cache
python scripts/build_public_data.py
python scripts/validate_public_data.py

# 单独获取 GMT 中国数据到不提交 Git 的 data/local/
# 先阅读该目录 README 和上游条款；此参数不构成再分发授权
python scripts/fetch_public_data.py --include-local --acknowledge-terms
python scripts/validate_public_data.py --include-local
```

下载锁定上游 **commit SHA**，不是会漂移的 `main/master` 链接；大小和 SHA256 不匹配会失败，不会静默覆盖原文件。城市完整源文件约 19 MB，只作为可重建缓存，不重复入库。已入库基础地理与构造数据约 **22 MB**，地震目录（含 ComCat 原始分块与区域目录原文）约 **40 MB**。

完整溯源：`data/metadata/sources.lock.json`；派生操作与校验值：`data/metadata/derivatives.json`；首次完整校验：`data/metadata/validation-2026-10-09.json`。

## 与原有绘图脚本的关系

旧脚本面向 Windows / GMT5，依赖 `sheng.gmt`、`shi.gmt`、`xian.gmt` 等特定文件名。本次不伪造这些文件，也不把省界改名为市县界。新数据可独立使用；CAFD 文件可由旧脚本的 `CN-faults.gmt` 入口识别，城市中文标注与投影仍需按运行平台测试。详见 [数据说明](data/README.md)。
