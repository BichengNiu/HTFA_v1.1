# Data Dubai DED 企业注册主表 下载与月度聚合

从迪拜官方开放数据门户下载 DED（迪拜经济局）企业注册主表全量快照，并自动
按月聚合"新增执照数"，与官方公布数字对比后写入阿联酋.xlsx。

## 官方数据源

- 数据集页面：[Commerce Registry](https://data.dubai/en/l/460521?com_dda_data_and_statistics_ThemeId=36962)
- 数据集说明：迪拜企业主记录集中登记库（注册序号、公司名、法律形式、国籍、
  登记类型、执照号/商业号、资本、发照/到期/注销日期）。
- 注意：旧门户 dubaipulse.gov.ae 的 `ded_license_master` 已整体迁移至
  data.dubai（301 重定向），本脚本默认走新门户的 dataset-download 接口。

## 一键更新（推荐）

双击：

`update_ded_all.bat`

等价于依次执行：

```powershell
python -u fetch_ded_license.py          # 1. 下载最新快照 + 企业/执照号首现筛重聚合
python -u build_monthly_ded_sheet.py    # 2. 合并写入 阿联酋.xlsx 的「月度_DED」sheet
```

每个月运行一次（快照每月更新）。脚本仅使用 Python 标准库 + openpyxl。

## 输出文件（DED_data/）

| 文件 | 说明 |
|---|---|
| `raw/commerce_registry_<快照时间>_*.csv.gz` | 原始全量快照（gzip 约 58 MB） |
| `monthly_new_licenses.csv` | 月度新增（按记录行数）：`month, new_licenses` |
| `monthly_counts.csv` | 三序列：`month, records`（记录行数）`, enterprises`（新增企业，企业号首现）`, licences`（新增执照，执照号首现） |
| `monthly_diff.csv` | （可选）快照差分序列：`month, added_records, added_enterprises`，由 diff_snapshots.py 生成 |
| `monthly_by_type.csv` | 月度 × 法律形式明细 |
| `schema_report.txt` | 字段清单、日期解析质量、样例数据 |
| `fetch_manifest.json` | 抓取时间、来源、SHA-256、行数、日期范围等清单 |

## 阿联酋.xlsx 的「月度_DED」sheet

三列对比（识别号首现筛重口径）：

| 列 | 含义 | 更新方式 |
|---|---|---|
| 迪拜:新增企业数(企业号首现筛重) | `commerce_number` 在快照中**最早发照月份**=企业新增月份；该企业号在其他月份的记录全部筛除（剔除占位 `'0'`） | 自动（fetch_ded_license.py） |
| 迪拜:新增执照数(执照号首现筛重) | `main_license_number` 最早发照月份=执照新增月份；同号重复记录筛除 | 自动（fetch_ded_license.py） |
| 迪拜:新发执照数(官方口径) | DET/迪拜媒体办公布的官方数字 | 手工维护 `official_ded_monthly.csv` |

**筛重原理**：单期存量快照中，同一企业号（多执照/续期）会出现在多个发照月份。
把"之前月份已出现过的号"全部筛掉后，每月剩下的就是当月真实新增——不需要第二期快照。
历史月份仍受存量快照性质影响（已注销企业不在库中）而低估，近期可信；
17.7% 无发照日期的记录无法归月，已排除。

另：`diff_snapshots.py` 保留为可选工具——等官方每月新快照发布后，可用相邻两期快照
差分做交叉验证（真实流量口径），用法见脚本注释。

官方数字维护方式：编辑 `official_ded_monthly.csv`（month, official_new_licenses,
note, source_url），官方季度/年度累计数字放在该期间最后一个月并注明口径，
然后重新运行 `build_monthly_ded_sheet.py`。

## 官方数字半自动抓取（fetch_official_news.py）

官方不发布结构化月度数据，数字以新闻稿形式发布。抓取器流程：

```powershell
# 1. 抓取 news_urls.txt 里的新闻稿，提取数字 → official_pending.csv（待确认）
python -u fetch_official_news.py

# 2. 人工检查 pending 后，一键合并进 official_ded_monthly.csv（同月已有值自动跳过）
python -u fetch_official_news.py --apply
python -u build_monthly_ded_sheet.py   # 3. 重新合并进 阿联酋.xlsx
```

- 每月看到官方新数字时，把新闻 URL 追加到 `news_urls.txt`（一行一个）再运行即可；
- 提取结果含原文片段，必须人工确认口径（月度/季度/半年/全年）；
- 已知缺陷：Media Office 无公开列表 API，URL 需人工提供；
  gulfbusiness 等部分站点正文正则可能漏匹配（标题数字在 HTML 属性中）。

## 数据口径与可靠性

- **存量快照，非流量**：聚合数字 = 截至快照时点登记库中现存记录按发照日期
  分布。已注销/移除的历史企业不在库中，因此越早的年份越低估
  （2020 覆盖率约 36%，2021 约 56%，2022H1 约 72%，近期 70%+）。
- **执照数 ≠ 企业数**：主表是企业主记录（每企业一条）；官方"新执照"含多执照。
- 覆盖范围：迪拜 DED 系统（含自由区公司在迪拜大陆的分支 0.15%），
  不含自由区自己颁发的执照。
- 17.7% 记录无发照日期（历史遗留），已排除；占位年份（如 0001）已过滤。
- 完整性与溯源：快照 SHA-256 记录在 fetch_manifest.json；解压字节数与官方
  元数据完全一致（已验证）。

## 认证说明（如未来接口要求登录）

下载接口当前公开可用。若未来改为需要登录，请求会被重定向到
`smartsso.dubai.gov.ae`（UAE Pass / Dubai ID + OTP），脚本会明确报错。
携带会话方式：

```powershell
python -u fetch_ded_license.py --header "Cookie: JSESSIONID=xxx; ..."
python -u fetch_ded_license.py --cookies-file cookies.txt
```

## 参数速查

| 参数 | 作用 |
|---|---|
| `--dataset-id <id>` | 更换 data.dubai 数据集编号（默认 460521） |
| `--url <直链>` | 直接下载指定数据文件，绕过页面与接口发现 |
| `--page <URL>` | 退回旧门户 dubaipulse 的 datafiles 链接发现流程 |
| `--format csv|json` | 下载文件格式（默认 csv） |
| `--date-col <列名>` | 指定发照日期列（默认自动识别 issue_date） |
| `--type-col <列名>` / `--no-type` | 指定/关闭类型明细 |
| `--skip-download` | 用 raw/ 里最新快照重新处理，不下载 |
| `--limit N` | 只处理前 N 行（测试用） |