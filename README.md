# FAERS 药物警戒信号检测工具箱 · FAERS Pharmacovigilance Signal Detection Toolbox

> 输入药品通用名，自动做**不成比例分析（disproportionality analysis）**，
> 输出该药「异常聚集的不良反应 Top 榜」——一套零成本、可复现、监管公认方法学的药物警戒（PV）信号检测工具。
>
> **支持两种数据源**：本机官方 FAERS/AERS 季度原始数据（**离线、推荐**）或 FDA openFDA 在线 API。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13-蓝色.svg)](https://www.python.org)
[![Offline](https://img.shields.io/badge/离线可用-内嵌运行环境-brightgreen.svg)](#离线本地模式推荐)

---

## 🚀 最快开始：双击启动器

**Windows 用户直接双击 `启动器.bat`**，浏览器会自动打开一个游戏启动器风格的控制面板：

![启动器示意](docs/launcher-preview.png)

在面板里可以：
- 看到每个工具的**实时运行状态**（未启动 / 运行中）
- 点 **▶ 启动** 后台拉起工具，就绪后卡片变为 **🌐 打开 / ■ 停止**
- 点 **🔍 扫描本机数据目录** 自动找出本机所有 FAERS 数据文件夹

| 工具 | 端口 | 说明 |
|---|---|---|
| 💊 **FAERS 本地信号检测** | 8502 | 读本机季度原始数据，**全程离线**，数据最全 |
| 🌐 **FAERS 在线检测** | 8501 | 走 FDA openFDA API，需联网，适合临时快查 |

> 整个文件夹**自带 Python 运行环境**（`python/` 目录），无需在电脑上安装 Python、无需配置环境变量。
> 把整个文件夹拷到 U 盘或发给同事，对方双击 `启动器.bat` 即可使用。

---

## 功能特性

- **两种数据源**：本地官方季度原始数据（离线）／ openFDA 在线 API。
- **三方法互为印证**：ROR（报告比值比）、PRR（比例报告比 + χ²）、BCPNN-IC（贝叶斯信息分量）。
- **国际信号标准打标**：强（3/3 指标达标）/ 中（2/3）/ 弱（1/3），规则可审计。
- **原始病例导出**：除信号榜外，可导出含该药的**全部报告明细**（人口学 + 用药 + 不良反应 + 结局）。
- **兼容 2004 年至今**：同时支持新命名 `faers_ascii_*.zip` 与旧命名 `aers_ascii_*.zip`（AERS 于 2012 年更名）。
- **自动化**：GitHub Actions 定时检测 + 自动月报。

---

## 目录结构

```
faers-pv-signals/
├── 启动器.bat                    # ⭐ 一键入口：启动游戏风格控制面板
├── launcher.py                   #    启动器源码（管理各工具的启停）
├── python/                       #    内嵌 Python 3.13 运行环境（已装好全部依赖）
│
├── faers_local_app.py            # 💊 本地离线检测应用（Streamlit）
├── faers_local_signals.py        #    本地检测核心：流式扫描季度 zip
├── streamlit_faers_app.py        # 🌐 在线检测应用（openFDA API）
├── faers_signal_detection.py     #    信号检测算法层：ROR/PRR/χ²/IC
├── faers_openfda_ingest.py       #    在线取数层（分页拉取并扁平化为 CSV）
│
├── notebooks/
│   ├── severity_model.ipynb      #    严重性评价建模（逻辑回归/随机森林）
│   └── build_severity_notebook.py
├── scripts/build_report.py       #    CI 用：汇总多品种 CSV → Markdown 月报
├── .github/workflows/
│   └── signal-detection.yml      #    定时检测 + 自动提交月报
├── docs/                         #    业务说明.html / 操作 SOP.html
├── examples/                     #    输出示例
├── exports/                      #  （自动生成）导出的原始病例 CSV
├── logs/                         #  （自动生成）各工具运行日志
├── README.md  CHECKLIST.md  RESUME.md  LICENSE  requirements.txt
└── setup_github.bat / .sh        #    发布到 GitHub 的一键脚本
```

> 📋 **首次运行前必读**：[CHECKLIST.md](CHECKLIST.md) —— 环境检查、依赖安装、常见报错速查。

---

## 离线本地模式（推荐）

### 数据准备
需要 FDA 官方 FAERS/AERS 季度原始数据（形如 `faers_ascii_2018Q1.zip` 的压缩包），
可从 FDA 官网下载，或直接使用已有的数据目录。

### 界面操作
启动本地检测应用后，在左侧：

1. **① 数据文件夹**
   - 点 **🔍 自动查找** → 自动扫描 C~J 盘，列出所有含 FAERS 数据的目录 → 下拉切换
   - 也可直接从资源管理器地址栏**复制路径粘贴**到输入框
   - 选中后会显示 `✅ 发现 N 个季度：20XXQX ~ 20XXQX`
2. **② 检测参数**
   - 起始年 / 截止年（自动按目录内数据范围填充）
   - 药品通用名（如 `ASPIRIN`）
   - **用药角色**：`ALL` 全部 / `PS` 首要怀疑（更严谨）/ `SS` 次要 / `C` 并用 / `I` 相互作用
   - **药名模糊匹配**：勾选后可覆盖 `ASPIRIN 81MG`、`BAYER ASPIRIN` 等变体写法
   - 输出 Top-N 信号数
3. 点 **🚀 开始检测** → 进度条显示逐季度处理进度 → 出 Top 信号榜

### 命令行（等价）

```bash
# 信号检测
python faers_local_signals.py --drug ASPIRIN --year-from 2023 --year-to 2025 --top 25

# 指定数据目录 + 只看首要怀疑药 + 模糊匹配
python faers_local_signals.py --drug "ASPIRIN" --data-dir "F:\数据\fares" \
       --role PS --fuzzy --top 30 --out signals_aspirin.csv
```

---

## 📦 导出原始病例数据

除了信号榜，还可以导出**含该药的全部报告明细**（病例级），用于自行二次分析。

**界面**：本地检测应用底部「📦 导出原始病例数据」→ 点「⬇️ 导出病例数据」
→ 存到 `exports/cases_<药品>_<起年>_<止年>.csv`，并提供下载按钮与预览。

**命令行**：

```bash
python faers_local_signals.py --drug ASPIRIN --year-from 2018 --year-to 2025 \
       --extract cases_aspirin_2018_2025.csv
```

导出字段（17 列）：

| 类别 | 字段 |
|---|---|
| 标识 | `primaryid`、`caseid`、`event_dt`（事件日期） |
| 人口学 | `age`、`age_cod`、`sex`、`wt`、`reporter_country`、`occr_country` |
| 用药 | `drug_name`、`drug_role`、`drug_ai`、`drug_route` |
| 不良反应 | `reactions`（该报告全部 PT，`\|` 分隔）、`n_reactions` |
| 结局 | `outcome_codes`、`serious` |

- 文件为 **UTF-8 BOM** 编码，Excel 双击直接打开不乱码。
- `serious=Y` 依据结局代码 `DE/LT/HO/DS/CA/RI`（死亡/危及生命/住院/残疾/先天异常/其他严重）判定。
- ⚠️ 年份跨度越大越慢（需逐季度扫描），建议先用 2–3 年试跑确认格式，再扩到全量。

---

## 在线模式（openFDA API）

```bash
pip install -r requirements.txt

# 取数（可选，生成候选词用）
python faers_openfda_ingest.py --drug ASPIRIN --max 2000 --date_from 2023-01-01

# 信号检测
python faers_signal_detection.py --drug ASPIRIN --csv faers_aspirin.csv --top_terms 25

# 交互 Demo
streamlit run streamlit_faers_app.py
```

打开浏览器 → 输入大写药名（如 `ASPIRIN`）→ 点「开始检测」→ 查看 Top 信号榜并下载 CSV。

> 匿名限速约 40 次/分，可在界面填入免费 API Key 提速。
> **企业内网常见问题**：单次响应体过大时可能被网络重置，此时请改用**本地离线模式**。

---

## 方法学

四格表（时间窗内同口径）：

|          | 反应 Y | 非 Y |
|----------|--------|------|
| 药 X     |   a    |  b   |
| 非 X     |   c    |  d   |

- **ROR** = (a·d)/(b·c)，以 95% CI 下限 > 1 且有统计意义。
- **PRR** = [a/(a+b)] / [c/(c+d)]，信号标准：PRR ≥ 2 且 χ² ≥ 4 且 a ≥ 3。
- **IC**（BCPNN）= log₂ 信息增益，信号标准：IC025（下限）> 0。

三指标全中 = **强信号**，二中 = **中信号**，一 = **弱信号**。

---

## 关键实现说明（避坑）

### 在线模式
1. **查询 URL 必须手工编码**：`urllib.parse.quote(search, safe=':+()"')` 保留 openFDA 搜索语法
   的 `+`(AND) 与 `:`；若交给 `requests` 的 `params=` 会自动转义掉，导致查询失效或数字错乱。
2. **反应词检索须带引号 + 时间窗**：`patient.reaction.reactionmeddrapt:"Chest pain"` 且加
   `receivedate:[YYYYMMDD TO YYYYMMDD]`，保证四格表口径自洽。
3. **openFDA `count` 分面对高基数字段会稳定 500**：故「自动发现」改用分页拉取报告样本 +
   本地统计频次，而非 `count=patient.reaction.reactionmeddrapt`。
4. **`fields` 参数不被 openFDA 支持**（返回 400），无法用其裁剪响应体。

### 本地模式
5. **数据格式**：`$` 分隔、latin-1 编码；`DEMO`(报告) / `DRUG`(用药) / `REAC`(不良反应) / `OUTC`(结局)。
6. **列索引必须按表头名动态定位**：早期 AERS 没有 `prod_ai` 列，硬编码索引会取错字段。
7. **药名比较要按字节**：`parts[i].upper()` 得到 bytes，与 str 比较恒为 False，
   必须先把药名 `.encode("latin-1")`。
8. **Windows 上 `netstat` 输出是 GBK**：须用 `.decode("latin-1", errors="ignore")`，
   按 utf-8 解码会抛 `UnicodeDecodeError`。

---

## 自动化（GitHub Actions）

`.github/workflows/signal-detection.yml` 实现两步流水线：

1. **detect**：每月 1 号 06:00 UTC（或手动 / 改检测脚本即触发）对 `matrix.drug` 中的品种
   跑 `faers_signal_detection.py`，结果以 artifact 留存 90 天。
2. **report**：下载所有 artifact，用 `scripts/build_report.py` 汇总成 Markdown 月报
   （含总览表、新强信号对比、各品种明细），并自动提交到 `reports/`。

> 提速 / 降限频：在仓库 **Settings → Secrets** 添加 `OPENFDA_API_KEY`（免费 key）。

## 发布到 GitHub

```bash
git init && git add . && git commit -m "init: FAERS PV toolbox"
git remote add origin <你的仓库URL>
git push -u origin main
```

> 仓库已用 `.gitignore` 排除本地产物（`exports/`、`logs/`、`__pycache__/` 等）。
> 注意：`python/` 运行环境约 400MB、含数千文件，通常**不建议**提交到 Git——
> 如需随仓库分发，请确认仓库容量限制，或改为在 README 中说明下载方式。

## 文档

- `docs/FAERS信号检测-临床研发业务说明.html` —— 一页式业务说明，对接 MAH 药物警戒职责（PSUR / RMP / 说明书沟通）。
- `docs/FAERS信号检测-操作SOP.html` —— 操作 SOP：怎么跑、怎么判读、怎么归档，含角色职责与记录表模板。
- `CHECKLIST.md` —— 首次运行必读检查清单（环境/依赖/报错速查）。
- `RESUME.md` —— 可贴进简历的项目描述（简版 + 展开版）。

---

## 局限与合规

- FAERS 为美国自发报告库，存在报告偏倚与漏报；**信号只提示关联，不能证明因果**。
- **适应症混杂**：老年人常用药的 Top 信号常出现 Pneumonia、Fall、Arthritis 等基础疾病或
  合并用药相关事件，**不代表药物导致这些事件**，需结合临床与流行病学数据判断。
- 数据以欧美人群为主，结论须结合中国人群与国内 ADR 监测数据再判断。
- 本工具是持有人 PV 体系的**增效工具**，**不替代**药物警戒质量管理体系（QMS）与 qualified person 的专业判读。
- 数据来源：FDA openFDA / FAERS 官方季度数据（公开、免费、免授权）。

---

## 许可证

[MIT](LICENSE) — 可自由用于学习与内部研究；用于商业或监管提交请确保符合所在地法规。
