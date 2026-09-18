# 用标准库构造一个合法的 .ipynb（避免手动拼 JSON 出错）
import json

cells = []

def md(text):
    cells.append({
        "cell_type": "markdown",
        "metadata": {},
        "source": text.splitlines(keepends=True),
    })

def code(text):
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(keepends=True),
    })

# ----------------------------------------------------------------------
md("""# FAERS 不良反应「严重性评价预测」建模框架

**目标**：基于一份药物不良反应报告的结构化字段，预测该报告是否「严重」
（死亡 / 住院 / 致残 / 危及生命 / 先天异常 / 需干预，任一标准即算严重）。

**输入**：`faers_openfda_ingest.py` 产出的 `faers_*.csv`（一行 = 一份报告）。

**建模思路**：
1. 数据加载与类别不平衡诊断
2. 特征工程（数值 / 类别 / 文本）
3. 基线模型：逻辑回归（`class_weight` 处理不平衡）
4. 进阶模型：随机森林
5. 评估：AUC / PR-AUC / ROC / 混淆矩阵 / 分类报告
6. 特征重要性解读

> 这是**框架**，每格可直接运行。建议先用小规模数据（`--max 2000`）跑通，再放大。
""")

# ----------------------------------------------------------------------
code("""import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (roc_auc_score, average_precision_score,
                             roc_curve, classification_report,
                             confusion_matrix, ConfusionMatrixDisplay)

sns.set_theme(style="whitegrid")
RANDOM_STATE = 42
""")

# ----------------------------------------------------------------------
md("""## 1. 加载数据

读取取数脚本（openFDA）产出的 CSV。建议先用小规模数据跑通框架，再逐步放大到几万条。
""")

code("""CSV_PATH = "faers_aspirin.csv"   # 改成你实际跑出的文件名
df = pd.read_csv(CSV_PATH)
print("样本量:", len(df))
print("字段:", list(df.columns))
df.head(3)
""")

# ----------------------------------------------------------------------
md("""## 2. 目标变量与类别不平衡

FAERS 中**多数报告是严重的**（严重率往往 > 80%），这是典型的**类别不平衡**问题。
因此：
- 不能只看「准确率」（全预测为严重也能拿高准确率）
- 要看 **AUC** 和 **PR-AUC**，并把 `class_weight` 打开
""")

code("""# 目标变量 Y：取数脚本已处理成 0/1
y = df["is_serious"].astype(int)

serious_rate = y.mean()
print(f"严重报告占比: {serious_rate:.3f}  ({int(y.sum())}/{len(y)})")

# 各严重性子项占比（取数脚本已拆出）
sev_cols = [c for c in df.columns if c.startswith("serious_")]
if sev_cols:
    print("\\n各严重性子项占比:")
    print(df[sev_cols].astype(float).mean().round(3))
""")

# ----------------------------------------------------------------------
code("""# 年龄分布（严重 vs 非严重），直观感受特征差异
df["age_num"] = pd.to_numeric(df["patient_age"], errors="coerce")
plt.figure(figsize=(8, 4))
sns.histplot(data=df, x="age_num", hue="is_serious", bins=40, element="step")
plt.title("Age distribution by seriousness")
plt.xlim(0, 100)
plt.show()
""")

# ----------------------------------------------------------------------
md("""## 3. 特征工程

构造三类特征：
- **数值**：年龄、合并用药数、体重
- **类别**：性别、给药途径（低频合并为 OTHER）
- **文本**：不良反应术语 `reactions`（TF-IDF）

> 注意：openFDA 的 `primary_route` 是**编码值**（如 `041`），建模时当类别处理即可，不需解码。
""")

code("""# --- 数值特征 ---
df["age_num"] = pd.to_numeric(df["patient_age"], errors="coerce")
df["ndrugs"]  = pd.to_numeric(df["num_drugs"], errors="coerce").fillna(0)
df["weight"]  = pd.to_numeric(df["patient_weight"], errors="coerce")

# --- 类别特征：性别（1=男, 2=女, 0/空=未知）---
sex_map = {"1": "male", "2": "female"}
df["sex_cat"] = df["patient_sex"].astype(str).map(sex_map).fillna("unknown")

# --- 类别特征：给药途径（保留 Top20，其余合并）---
top_routes = df["primary_route"].value_counts().head(20).index
df["route_cat"] = (df["primary_route"]
                   .where(df["primary_route"].isin(top_routes), "OTHER")
                   .fillna("OTHER"))

# --- 文本特征：不良反应术语 ---
df["reactions_text"] = df["reactions"].fillna("").astype(str)

num_cols = ["age_num", "ndrugs", "weight"]
cat_cols = ["sex_cat", "route_cat"]
text_col = "reactions_text"

X = df[num_cols + cat_cols + [text_col]]
print("特征矩阵形状:", X.shape)
""")

# ----------------------------------------------------------------------
md("""## 4. 训练 / 测试分割

按 80/20 分割，用 `stratify=y` 保持严重率分布。不靠过采样，而是把不平衡处理交给模型的 `class_weight`。
""")

code("""X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y)

print("Train:", X_train.shape, " Test:", X_test.shape)
""")

# ----------------------------------------------------------------------
md("""## 5. 预处理管道（ColumnTransformer）

把「数值标准化 + 类别 OneHot + 文本 TF-IDF」统一封装进一个 `Pipeline`，
保证训练/测试用同一套变换，且避免数据泄漏。
""")

code("""preprocess = ColumnTransformer(
    transformers=[
        ("num", StandardScaler(), num_cols),
        ("cat", OneHotEncoder(handle_unknown="ignore"), cat_cols),
        ("txt", TfidfVectorizer(max_features=500, stop_words="english",
                                ngram_range=(1, 2)), text_col),
    ])

# 预览预处理后的维度（文本被展开成几百列）
Xp = preprocess.fit_transform(X_train)
print("预处理后维度:", Xp.shape)
""")

# ----------------------------------------------------------------------
md("""## 6. 基线模型：逻辑回归

简单、可解释，作为性能底线。
""")

code("""lr = Pipeline([
    ("pre", preprocess),
    ("clf", LogisticRegression(max_iter=1000, class_weight="balanced",
                               random_state=RANDOM_STATE)),
])
lr.fit(X_train, y_train)
proba_lr = lr.predict_proba(X_test)[:, 1]
pred_lr  = (proba_lr >= 0.5).astype(int)

print("LogReg       AUC   :", round(roc_auc_score(y_test, proba_lr), 4))
print("LogReg       PR-AUC:", round(average_precision_score(y_test, proba_lr), 4))
print(classification_report(y_test, pred_lr, target_names=["非严重", "严重"]))
""")

# ----------------------------------------------------------------------
md("""## 7. 进阶模型：随机森林

捕捉非线性与特征交互。`class_weight='balanced_subsample'` 处理不平衡。

> 若你已装 XGBoost，可直接把下面 `RandomForestClassifier` 换成
> `XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.05,
>                subsample=0.9, colsample_bytree=0.9, eval_metric="logloss")`，
> 接口完全一致。
""")

code("""rf = Pipeline([
    ("pre", preprocess),
    ("clf", RandomForestClassifier(n_estimators=300, max_depth=None,
                                   class_weight="balanced_subsample",
                                   n_jobs=-1, random_state=RANDOM_STATE)),
])
rf.fit(X_train, y_train)
proba_rf = rf.predict_proba(X_test)[:, 1]
pred_rf  = (proba_rf >= 0.5).astype(int)

print("RandomForest AUC   :", round(roc_auc_score(y_test, proba_rf), 4))
print("RandomForest PR-AUC:", round(average_precision_score(y_test, proba_rf), 4))
print(classification_report(y_test, pred_rf, target_names=["非严重", "严重"]))
""")

# ----------------------------------------------------------------------
md("""## 8. 评估：ROC 曲线 + 混淆矩阵

ROC 看整体排序能力；混淆矩阵看阈值 0.5 下的错分情况。
""")

code("""best_proba = proba_rf   # 选用随机森林；想比较 LR 就改成 proba_lr
best_pred = pred_rf

# ROC
fpr, tpr, _ = roc_curve(y_test, best_proba)
plt.figure(figsize=(6, 5))
plt.plot(fpr, tpr, label=f"AUC={roc_auc_score(y_test, best_proba):.3f}")
plt.plot([0, 1], [0, 1], "k--", alpha=.5)
plt.xlabel("False Positive Rate"); plt.ylabel("True Positive Rate")
plt.title("ROC Curve"); plt.legend(); plt.show()

# 混淆矩阵
cm = confusion_matrix(y_test, best_pred)
disp = ConfusionMatrixDisplay(cm, display_labels=["非严重", "严重"])
disp.plot(cmap="Blues"); plt.title("Confusion Matrix @0.5"); plt.show()
""")

# ----------------------------------------------------------------------
md("""## 9. 特征重要性

随机森林的特征重要性，快速看哪些字段对「严重性」贡献最大。

> 文本特征（TF-IDF）被展开成几百维，这里只看**结构化特征**的重要性更直观。
""")

code("""pre = rf.named_steps["pre"]
clf = rf.named_steps["clf"]
feat_names = (num_cols
              + list(pre.named_transformers_["cat"].get_feature_names_out(cat_cols)))
importances = clf.feature_importances_[:len(feat_names)]

imp = (pd.DataFrame({"feature": feat_names, "importance": importances})
         .sort_values("importance", ascending=False).head(15))
plt.figure(figsize=(8, 5))
sns.barplot(data=imp, x="importance", y="feature", color="#4C72B0")
plt.title("Top structured-feature importances (RandomForest)")
plt.show()
""")

# ----------------------------------------------------------------------
md("""## 10. 阈值调优（可选）

严重率极高时，默认 0.5 阈值会让「非严重」几乎全被预测为严重。
可在验证集上用 Youden's J 选一个更合理的阈值，或直接报告 AUC/PR-AUC 即可。
""")

code("""from sklearn.metrics import precision_recall_curve
prec, rec, thr = precision_recall_curve(y_test, best_proba)
j = rec - (1 - prec)            # Youden's J 的 PR 空间近似
best_idx = np.argmax(j)
print(f"建议阈值={thr[best_idx]:.2f}  precision={prec[best_idx]:.3f}  "
      f"recall={rec[best_idx]:.3f}")
""")

# ----------------------------------------------------------------------
md("""## 11. 下一步

1. **信号检测模块**：在 `faers_openfda_ingest.py` 基础上加 ROR / PRR 不成比例分析，
   输出某药的 Top 异常不良反应榜（详见 `AI项目-选题1-FAERS信号检测.md`）。
2. **模型固化**：用 `joblib.dump(rf, "severity_model.pkl")` 保存 Pipeline，新报告批量打分。
3. **交互 Demo**：用 Streamlit 做一个「输入一份报告 → 预测是否严重 + 给出 Top 信号」的小应用，
   直接放进简历作品集。
4. **扩大数据**：换更多药物 / 更长周期，重跑本 notebook 看泛化。

> 本框架与 **WQU Data Science Lab** 同步推进：Lab 学 Python→Pandas→ML，
> 本 notebook 练**真实医药数据**，二者正好闭环——这份作品集在求职/转岗时比一纸在线学位更实在。
""")

# ----------------------------------------------------------------------
notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.13"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT = "severity_model.ipynb"
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(notebook, f, ensure_ascii=False, indent=1)
print("已生成", OUT, "，共", len(cells), "个 cell")
