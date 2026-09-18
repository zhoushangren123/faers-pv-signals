# 简历项目描述 · FAERS 药物警戒信号检测流水线

> 可直接复制到简历/作品集。简版用于条目一行，展开版用于项目详述。

## 简版（一行，约 45 字）

基于 FDA openFDA 构建 FAERS 药物警戒信号检测流水线（ROR/PRR/BCPNN），含 AI 严重性评价、Streamlit 交互 Demo 与 GitHub Actions 自动月报。

## 展开版（项目详述，STAR 风格）

**FAERS 药物警戒信号检测流水线**　|　Python · scikit-learn · Streamlit · GitHub Actions
*2026　个人项目（药学 × AI 交叉方向）*

- **背景**：对接持有人（MAH）药物警戒法定信号检测职责（ICH E2E / PSUR / RMP），用零成本公开数据做可复现的安全信号初筛。
- **数据**：FDA openFDA 公开不良反应库（免费、免 key、千万级报告），自主编写分页取数脚本扁平化。
- **方法**：实现 ROR / PRR / χ² / BCPNN-IC 四种国际通行不成比例分析，按强（3/3）/ 中（2/3）/ 弱（1/3）自动分级；实测 ASPIRIN 窗口内 N=619 万，Chest pain 判为强信号（ROR 3.03 / IC 1.51）。
- **建模**：随机森林 + 逻辑回归（class_weight 平衡）做不良反应严重性评价预测，ColumnTransformer 管道防数据泄漏。
- **产品**：Streamlit 交互 Demo（输入药名→实时 Top 信号榜 + CSV 下载），配套一页业务说明与操作 SOP 对接临床研发工作。
- **工程**：GitHub Actions 定时/手动跑检测，自动汇总 Markdown 月报并提交仓库，含 429 退避重试与月环比「新强信号」预警。
- **合规**：明确输出为关联提示而非因果结论，定位为持有人 PV 体系增效工具，不替代 QMS 与 qualified person 判读。

## 技术栈（关键词，便于 ATS / 搜索匹配）

Python · pandas · scikit-learn · Streamlit · GitHub Actions (CI/CD) · 药物警戒 (Pharmacovigilance) · 不成比例分析 (Disproportionality Analysis) · ROR / PRR / BCPNN · openFDA / FAERS · 临床研发 (Clinical R&D)

## 一句话定位（社交/求职信用）

用 AI 把"某药哪些不良反应被报告得异常多"自动算出来——一套零成本、可复现、对接药物警戒合规职责的开源工具链。
