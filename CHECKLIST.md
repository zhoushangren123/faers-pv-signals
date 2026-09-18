# 首次运行必读 · 检查清单（FAERS PV 信号检测）

> 第一次在本机跑这个项目前，按顺序勾一遍。预计准备时间 5–15 分钟（主要花在装依赖）。

## 0. 环境检查（必做）

- [ ] **Python 3.9+** 已安装并加入 PATH。验证：`python --version`（Windows）/ `python3 --version`（macOS/Linux）能看到版本号。
- [ ] **能联网访问 `api.fda.gov`**（FAERS 数据来自 FDA openFDA，免 key，但需联网）。
- [ ] （仅当你要发布到 GitHub 时）**Git 已安装**：`git --version` 有输出。

## 1. 装依赖（二选一）

- **方式 A（推荐，零命令）**：直接双击 `run.bat`（Windows）或运行 `./run.sh`（macOS/Linux）。脚本会检测 `streamlit` 是否缺失，缺失则自动 `pip install -r requirements.txt`。
- **方式 B（手动）**：
  ```bash
  pip install -r requirements.txt
  ```
  依赖含：streamlit / requests / pandas / scikit-learn / matplotlib / seaborn / jupyter / notebook。

> ⏱ 首次安装约需几分钟，依赖较多属正常。若 `pip` 下载慢，可加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` 用国内镜像。

## 2. 启动交互 Demo（日常用法）

- [ ] 启动：双击 `run.bat` / `./run.sh`（或手动 `streamlit run streamlit_faers_app.py`）。
- [ ] 浏览器自动打开 `http://localhost:8501`（没自动开就手动访问）。
- [ ] 输入**大写**药品通用名（如 `ASPIRIN`）→ 选「自动发现」→ 点「开始检测」→ 等进度条 → 看 Top 信号榜、下载 CSV。

## 3. 命令行跑信号检测（可选）

```bash
# 从取数 CSV 提取候选词（需先跑 ingest）
python faers_openfda_ingest.py --drug ASPIRIN --max 2000 --date_from 2023-01-01
python faers_signal_detection.py --drug ASPIRIN --csv faers_aspirin.csv --top_terms 25

# 或直接指定反应词（快）
python faers_signal_detection.py --drug ASPIRIN --reactions "Gastric haemorrhage;Headache;Nausea"
```

## 4. 发布到 GitHub（可选）

- [ ] 先在 GitHub 网页**新建空仓库**（不要勾选自动生成 README/LICENSE，避免 push 冲突）。
- [ ] 运行 `setup_github.bat` / `./setup_github.sh`，粘贴仓库 URL。
- [ ] 首次会提示填 `git user.name` / `git user.email`（只问一次）。

## 5. 提速 / 降限频（可选）

- openFDA 匿名限速约 **40 次/分钟**。要提速：去 https://open.fda.gov/apis/ 免费申请 key，在仓库 Secrets 加 `OPENFDA_API_KEY`（CI 用），或命令行 `--api_key <你的key>`。
- 监测更多品种：改 `.github/workflows/signal-detection.yml` 里的 `matrix.drug` 列表（大写通用名）。

## 6. 常见报错速查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| `python` 不是内部命令 | Python 未加入 PATH | 重装 Python 并勾选 "Add to PATH" |
| 依赖安装超时/失败 | 网络慢 | 用国内镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| 启动后白屏/打不开 | 浏览器没自动开 | 手动访问 `http://localhost:8501` |
| 检测返回空或很少信号 | 药名没大写 / 时间窗太窄 | 药名用大写通用名；放宽 `--date_from` |
| openFDA 返回 429 | 触发匿名限速 | 等 1 分钟重试，或填 API key |
| `git push` 被拒 | 远程仓库含 README 冲突 | 建空仓库（不勾选生成文件）后重推 |

## 7. 合规提醒（务必读）

- 本工具输出**信号（关联提示），不是因果结论**，不能替代药物警戒 QMS 与 qualified person 判读。
- FAERS 为美国自发报告库，存在欧美人群偏倚，结论须结合中国人群与国内 ADR 监测数据再判断。
- 本项目作品集价值在「药学 × AI 复合能力展示」，不代表任何学历认证。
