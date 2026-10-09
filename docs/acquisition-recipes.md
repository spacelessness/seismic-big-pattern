# 补充数据获取配方

以下是**在可访问相应官方域名的环境中**执行的后续步骤，本次没有将这些命令的输出冒充已下载数据。所有新数据先放 `data/local/`，核验条款、元数据和质量后再决定是否发布。

## 1. USGS 地震目录：按固定时段获取

官方 API：<https://earthquake.usgs.gov/fdsnws/event/1/>。UTC 时间、支持 CSV/GeoJSON。单次查询上限 20,000 条；不要用 `limit=20000` 后就认为结果完整。

示例仅为 **2025 年全球 M≥5**，不是全历史目录，也不保证该阈值下所有地区/年代都完整：

```bash
mkdir -p data/local/usgs
# 先检查条数，再决定是否需要分月/分年
curl --fail --get 'https://earthquake.usgs.gov/fdsnws/event/1/count' \
  --data-urlencode 'starttime=2025-01-01T00:00:00' \
  --data-urlencode 'endtime=2025-12-31T23:59:59.999' \
  --data-urlencode 'minmagnitude=5'

curl --fail --get 'https://earthquake.usgs.gov/fdsnws/event/1/query' \
  --data-urlencode 'format=csv' \
  --data-urlencode 'starttime=2025-01-01T00:00:00' \
  --data-urlencode 'endtime=2025-12-31T23:59:59.999' \
  --data-urlencode 'minmagnitude=5' \
  --data-urlencode 'orderby=time-asc' \
  --output data/local/usgs/global_m5_2025.csv
```

若 count 超限，拆分时段；相邻时段接口边界是包含关系，按事件 `id` 去重，保留较新的 `updated` 版本。保存实际完整请求 URL、请求时间、响应条数、SHA256。空响应、HTTP 错误、HTML 错误页都不能当成有效目录。

保留 `magType`、`depth`（km）、`status`、误差等字段，不用统一震级下限掩盖不同年代/台网的完备性差异。中国区优先核对国家地震台网正式目录。

## 2. 地形：只取大尺度区域

GMT6 安装并能访问其数据服务器后：

```bash
mkdir -p data/local/topography
# 10m = 10 arc-minutes，不是 10 米
# 以下为分析矩形，非中国边界
# 根据 GMT 版本，首次请求会从远程服务器获取相应格网
gmt grdcut @earth_relief_10m -R70/140/0/60 \
  -Gdata/local/topography/east_asia_10arcmin.nc
gmt grdinfo data/local/topography/east_asia_10arcmin.nc
```

记录 GMT 版本、远程数据产品版本/来源、像元注册方式、经纬度范围、垂直单位及文件校验值。若需 05m/01m，按图幅精度逐步提高；不默认下载全球 15s。

## 3. 震源机制

- Global CMT 官方目录：<https://www.globalcmt.org/CMTfiles.html>；NDK 格式说明和月度文件由该页链接获取。
- 国家地震台网中心 CMT：<https://data.earthquake.cn/datashare/report.shtml?PAGEID=earthquake_dzzyjz>。

优先取所需时段/区域。保留参考文献、矩张量单位、矩心时刻/位置、震源时刻/位置、Mw 与解类型。绘制沙滩球前确认分量约定和 GMT `meca` 输入格式，不把原始张量列直接当作走向/倾角/滑动角。

## 4. WSM 地应力

入口：<https://doi.org/10.5880/WSM.2025.001>，先取得 CSV 和对应字段说明。GMT 中文手册也有当前示例：<https://docs.gmt-china.org/latest/dataset/WSM/>。

使用标准 CSV 解析器，不按字符串逗号简单拆分；引号内可能含逗号。保留坐标缺失、质量等级和测量类型标志。质量筛选条件、深度阈值和方向角约定应写入派生元数据，不能把全部记录当作同等可靠的现今主应力方向。

## 5. GNSS / 应变率

NGL 官方入口：<https://geodesy.unr.edu/>。

- IGS20 MIDAS：<https://geodesy.unr.edu/gps_timeseries/IGS20/midas/midas.IGS.txt>
- 字段说明：<https://geodesy.unr.edu/velocities/midas.readme.txt>
- GSRM：<https://geodesy.unr.edu/gsrm.php>

先下载字段说明，再解析台站速度；保留参考框架、有效观测跨度、不确定度、离群/阶跃处理信息。不同参考框架的速度矢量不可直接叠加。引用 Blewitt, Hammond & Kreemer (2018), DOI `10.1029/2018EO104623`，以及台站页要求的原始数据引用。

## 6. 官方行政边界

参见 [中国官方数据流程](china-official-data.md)。原始文件取得后建议用 QGIS/GDAL：检查真实 CRS、图层名和字段 → 筛选需要的图层 → 按需要重投影到目标坐标系 → 导出 GeoPackage 或 GeoJSON → 验证拓扑和岛屿/分离多边形 → 补齐来源/许可。不要用 `-a_srs` 改标签来冒充坐标转换；不存在一条未经核验即可自动“生成官方边界”的命令。
