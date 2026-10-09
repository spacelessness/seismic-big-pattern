# 第三方数据许可与引用

本仓库是不同来源数据的集合，**不对全部数据授予单一开源许可证**，也不改变已有 EQT 目录的权利状态。

| 数据 | 许可/状态 | 本仓库处理 |
|---|---|---|
| GEM 全球活动断裂 | CC BY-SA 4.0 | 原始与派生均保持该许可；保留署名、许可原文与变换记录 |
| PB2002 的 fraxen/Nordpil 转换版 | Open Data Commons Attribution License 1.0 | 保留原始声明，使用时注明 Peter Bird、Hugo Ahlenius / Nordpil |
| Natural Earth | Public Domain | 保留上游声明；建议署名 Made with Natural Earth |
| GMT 中文 CN-faults/CN-block/CN-border | 未发现统一明确 LICENSE；原数据和派生版权应分别核验 | 仅下载到忽略目录，提交 URL、版本锁、校验值和说明，不再分发数据 |
| 中国官方行政边界原始成果 | 以官方平台实际下载条款为准 | 本次未取得，不推断其为 Public Domain |
| 原有 EQT 文件 | 来源/许可证尚未随仓库提供 | 原样保留，不赋予新的开放许可 |
| 来源目录中的补充产品 | 各自产品条款，待下载时逐项核验 | 仅列来源，不视为已入库或已获再分发许可 |

## 必要署名

### GEM

Styron, Richard, and Marco Pagani (2020). The GEM Global Active Faults Database. *Earthquake Spectra*, 36(1_suppl), 160–180. <https://doi.org/10.1177/8755293020944182>。

来源 <https://github.com/GEMScienceTools/gem-global-active-faults>。许可全文见 [gem-LICENSE.txt](licenses/gem-LICENSE.txt)。筛选和格式转换是本仓库新增的改动，详见 `metadata/derivatives.json`；CC BY-SA 4.0 同样适用于相关派生数据，不能移除属性里的区域来源引文。

### PB2002

Bird, Peter (2003). An updated digital model of plate boundaries. *Geochemistry, Geophysics, Geosystems*, 4(3), 1027. <https://doi.org/10.1029/2001GC000252>。

GIS 转换：Hugo Ahlenius / Nordpil；GeoJSON 转换贡献者见 [pb-README.md](licenses/pb-README.md)。数据来源 <https://github.com/fraxen/tectonicplates>，许可声明见 [pb-LICENSE.md](licenses/pb-LICENSE.md)；完整法律条款链接 <https://opendatacommons.org/licenses/by/1-0/>。本仓库追加 GMT 线文件，不改变原 GeoJSON。

### Natural Earth

Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com.

作者 Tom Patterson、Nathaniel Vaughn Kelso 及其他贡献者。完整上游声明见 [ne-LICENSE.md](licenses/ne-LICENSE.md)。城市字段裁减、34 城市标注名单、重要城市筛选与去空河流图层是本仓库的加工，不代表上游或官方对其背书。

## 发布注意

公开可下载不等于允许所有用途或允许再次发布；论文许可不必然覆盖附件数据库。地图边界合规、数据许可证、地图审核是不同问题。对外发表须按实际用途核查；本集合不提供已审定地图，也不能作为工程设防或临震预报依据。
