# RTA Open Data — 官方数据源调研（6 个数据集核实用）

> 调研日期：2026-08-19 · 方法：逐端点在真实环境实测（HTTP 状态码、JSON 响应、匿名下载验证），所有 URL 均在本会话验证过。

## 0. 托管位置结论（重要）

RTA 的 6 个目标数据集**当前唯一官方载体 = Data Dubai 门户（`data.dubai`，Liferay 平台）**，RTA 是发布机构：

- 发布机构 RTA：`/o/c/issuingentities` 中 `id=88757`，`key=rta`，externalReferenceCode=`38d7271d-d3ae-453d-8193-db09719f7657`（在网共 **61 个数据集**）。
- 旧 **Dubai Pulse Open Data（`www.dubaipulse.gov.ae/data/...`）已整体死亡**：所有数据集页与文件页 301 → `https://data.dubai/`（新门户首页）。旧 CSV 直链不可再用。
- **`rtaopen.opendata.arcgis.com`（ArcGIS Hub）是空壳**：首页是默认建档页、0 个数据集；Hub 搜索 API 401。排除。
- **RTA 官网 `rta.ae/wps/portal/rta/ae/home/open-data`**：只有开放数据政策/法规栏目（agencies-legislation、traffic-road-legislations 等），无这 6 个数据集，页面明确链到 data.dubai。
- 数据 CDN：`cdn.data.dubai`（免认证文件下载）。
- 数据 API 网关：`apis.data.dubai`（需认证）＋ 老 token 服务 `api.dubaipulse.gov.ae/oauth/...`（仍在运行）。

## 1. 三个免认证的官方端点（核心）

### 1.1 枚举全部 RTA 数据集（目录）
```
GET https://data.dubai/o/c/datasets?pageSize=100&page={n}&filter=r_issuingEntityOfDataset_c_issuingEntityERC%20eq%20'38d7271d-d3ae-453d-8193-db09719f7657'
```
返回 61 条，每条含：`id`、`datasetName`（如 `bus_ridership`）、`title_i18n.en_US`、`dataAPIEndpoints`（REST 端点）、`format`、`frequencyOfUpdateToSDP`、`description_i18n`、`datasetURL` 等。

### 1.2 数据集文件清单（分页）
```
GET https://data.dubai/o/dda/data-services/dataset-download?datasetId={datasetId}&page={n}&pageSize=30&sortDir=desc
```
返回 `{"success":true,"data":{"pagination":{"total",...,"page_count","has_more"},"metadata":[{file_folder,download_link_validity,files:[{file_url,file_name,file_extension,file_size}]}]}}`
- `file_url` 是 **CDN 签名链接（匿名 GET 200 已验证）**，但 **`download_link_validity:600`（10 分钟）→ 枚举后须立即下载，勿缓存 URL**。
- `pageSize` 官方上限 30。

### 1.3 表内记录（行数据，缓存）
```
GET https://data.dubai/o/dda/data-services/dataset-metadata?datasetId={datasetId}            # 最多返回 7000 行缓存，JSON，无 token
GET .../dataset-metadata?datasetId={id}&download=true    # 同缓存；&cacheCheck=true 检查缓存是否就绪
```

### 1.4 数据 API（备选/全量，需 token）
```
GET  https://apis.data.dubai/open/rta/rta_{slug}-open-api            # 无 token → 401（已实测）
POST https://api.dubaipulse.gov.ae/oauth/client_credential/accesstoken?grant_type=client_credentials
     body: client_id={API Key}&client_secret={API Secret}            # → {access_token}，30 分钟有效
     Header: Authorization: Bearer {access_token}
     查询参数: ?limit=... &filter=attr=value AND/OR attr=... &限定属性名
```
API Key/Secret：在 data.dubai 申请数据集授权/注册后由邮件发放（免费，一次性，之后可无人值守）。

## 2. 六个数据集逐项（真实实测）

| # | 官方名（datasetName / title） | 落地页 | datasetId | 开放文件数 | API 端点（需 token） |
|---|---|---|---|---|---|
| 1 | bus_ridership — Bus Ridership Transactions | https://data.dubai/en/l/459803 | 459803 | 2060 个分片 | https://apis.data.dubai/open/rta/rta_bus_ridership-open-api |
| 2 | bus_passengers_trips_by_route_monthly — Bus Passengers Trips by Route Monthly | https://data.dubai/en/l/459793 | 459793 | 1 | https://apis.data.dubai/open/rta/rta_bus_passengers_trips_by_route_monthly-open-api |
| 3 | average_speed_per_line_buses — Average Speed of Buses for Each Line | https://data.dubai/en/l/459282 | 459282 | 4 | https://apis.data.dubai/open/rta/rta_average_speed_per_line_buses-open-api |
| 4 | marine_ridership — Marine Ridership | https://data.dubai/en/l/466229 | 466229 | 7 | https://apis.data.dubai/open/rta/rta_marine_ridership-open-api |
| 5 | marine_passengers_trips_by_station_monthly — Marine Passengers Trips by Station Monthly | https://data.dubai/en/l/466217 | 466217 | 1 | https://apis.data.dubai/open/rta/rta_marine_passengers_trips_by_station_monthly-open-api |
| 6 | taxis_and_number_of_trips_by_carrier_company_month — Taxis and Number of Trips by Carrier Company Monthly | https://data.dubai/en/l/469849 | 469849 | 1 | https://apis.data.dubai/open/rta/rta_taxis_and_number_of_trips_by_carrier_company_month-open-api |

### 2.1 列结构与口径（实测样本）
1. **Bus Ridership**（文件表头，注意官方拼写错误 `end_loaction` 与字段名下划线）：
   `end_loaction, end_zone, route_name, start_location, start_zone, txn_date, txn_subtype, txn_time, load_timestamp`
   （API `dataset-metadata` 返回列略不同：`txn_date, start_location, txn_type[值 CKO/CKI], route_name, start_zone, txn_time, end_location, end_zone, load_timestamp`）
2. **Bus Trips by Route Monthly**：`month, year, route_name, trips, load_timestamp`（month 为 "Apr"/4 等混合写法）
3. **Average Speed per Line**：`date, service_type, route_name, route_direction, average_speed, load_timestamp, time_period`（time_period 形如 `07:00 - 08:00`）
4. **Marine Ridership**（API 列）：`txn_date, txn_type[值如 Check], zone, txn_time, line_name, location, load_timestamp`
5. **Marine Trips by Station Monthly**：`marine_station, passengers_rids, month, year, marine_mode, load_timestamp`（在网 2515 行；注意官方命名 `passengers_rids`）
6. **Taxi Carrier Monthly**：`fleet_name, fleet_size, trips_num, load_timestamp, report_date`（在网 304 行，当前最新 report_date=2026-01-31）

### 2.2 关于「逐日资源」的重要澄清（实测发现）
- 平台上 `dataset-download` 列的 `file_folder` 形如 `bus_ridership_2026-07-21_18-21-27_0001`——**不是按日期命名，而是「导出批次+全局分片号」**。
- 抽查一个分片：**单个文件即约 105 万行、~140MB，内容时间跨度从 2017 一直覆盖到 2025+**（非严格单日）。即开放列表里每个分片是很大的历史切片。
- 开放列表只滚动保留**最近几次全量导出**：bus 现为 2060 个分片（69 页）、marine 仅 7 个分片（1 页）。**与旧平台「每天一个 CSV、marine 约 2600 个资源」的口径不同**——旧平台已死，该数字本次未能独立复核（Wayback 不可达）。
- 结论：免认证公开下载适合「当周/当批」与抽样；要干净的全量唯一历史，最稳妥是申请免费 API 授权（token）或用多个分片去重合并。

## 3. 保存结构与方案（Python 全自动）

```
raw/rta/open/<datasetId>_<slug>/manifest.json      # datasetId、抓取时间、pagination、file_folder→签名URL(含过期时间)
raw/rta/open/<datasetId>_<slug>/<file_folder>/<file_name>.csv.gz   # 匿名下载，注意实际是纯文本 CSV
raw/rta/open/<datasetId>_<slug>/rows/<date>.json    # dataset-metadata 缓存行（可选）
```
Python 要点：
- 用 `requests` 直接 GET 端点 1.1→1.2→CDN，全程免认证；CDN 链接 600s 过期 → 边枚举边下。
- 字段含逗号（地点名如 `Al Barsha, Lulu Supermarket 2`）→ 必须用 `csv.reader` / `pandas.read_csv(quoting=csv.QUOTE_ALL)` / DuckDB `read_csv_auto`，不能手工 split。
- 建表入库时统一字段名（修正官方 typo `end_loaction→end_location`、`passengers_rids→passengers_rides` 可选）。

## 4. 无人值守可行性
- ✅ **完全无人值守（免 token）**：目录枚举、文件清单、CDN 下载、缓存行，全部是公开 GET。风险点仅 CDN 链接 10 分钟有效期与文件体积（~140MB/片）。
- 🔑 **若要全量历史/规范化 API**：一次性免费申请授权拿 Key/Secret → token（30 分钟）→ `apis.data.dubai`。之后可无人值守（加 token 刷新逻辑）。
- ❌ 不推荐：rta.ae（无数据）、rtaopen ArcGIS Hub（空）、旧 dubaipulse（已 301）。
