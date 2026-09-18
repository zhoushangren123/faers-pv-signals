#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAERS 药物安全信号检测 · Streamlit 交互 Demo
===========================================
输入一种药品通用名 → 实时输出该药 **Top 异常不良反应榜**（潜在安全信号）。

特点：
  1. 零前置数据：默认分页拉取该药「报告样本」并在本地统计频次最高的不良反应作为
     候选词，再逐词做不成比例分析（ROR / PRR / BCPNN-IC）。
     （注：openFDA 的 count 分面对高基数字段会稳定 500，故采用记录采样+本地统计。）
  2. 也支持：上传取数脚本产出的 CSV 自动提词，或手动粘贴候选反应词。
  3. 关键坑已复用 faers_signal_detection 的 URL 编码逻辑（quote(safe=':+()"')），
     避免 requests 自动转义 +/: 导致查询失效。
  4. 逐词查询带进度条；用 @st.cache_data 做查询级缓存，重复检索瞬时返回。

指标与判定（国际通行药物警戒标准）：
  - ROR   报告比值比：a≥3 且 ROR 95%CI 下限 >1
  - PRR   比例报告比：a≥3 且 PRR≥2 且 χ²≥4
  - IC    贝叶斯信息分量(BCPNN)：IC025 > 0
  三项全中 = 强信号；两项 = 中；一项 = 弱。

运行：
  pip install -r requirements.txt
  streamlit run streamlit_faers_app.py
依赖：streamlit requests pandas matplotlib

免责声明：本 Demo 仅用于方法学与作品集演示，不构成任何医疗/监管结论。
"""

import os
import sys
import time

import pandas as pd
import requests
import streamlit as st
from urllib.parse import quote

# 复用同目录下的信号检测模块（字段名、URL 编码坑均已验证）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import faers_signal_detection as fsd  # noqa: E402

# 本地 FAERS 季度数据支持（可选；缺失时自动降级为纯在线模式）
try:
    import faers_local_signals as fls  # noqa: E402
    HAS_LOCAL = True
except Exception:
    fls = None
    HAS_LOCAL = False

API_BASE = fsd.API_BASE
REQUEST_DELAY = 0.3

# --------------------------------------------------------------------------
# 查询级缓存：同一 search 串的结果缓存 1 小时，避免重复网络请求
# --------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def cached_total(search: str, api_key: str) -> int:
    """带重试/限速退避的计数查询（复用模块逻辑，可被 Streamlit 缓存）。"""
    return fsd.api_total(search, api_key, REQUEST_DELAY)


# openFDA 的 count 分面接口对高基数字段（如 reactionmeddrapt，约 2.5 万唯一值）
# 会稳定返回 HTTP 500，因此「自动发现」改用分页拉取真实报告、在本地统计反应词频次。
SAMPLE_PAGES = 20         # 每页 5 条，共约 100 份报告作为候选词样本
PER_PAGE = 5              # 单条 ASPIRIN 记录可达 ~250KB，limit=5 单次约 1-2MB，避免大响应被网络重置


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_top_reactions(drug: str, date_from: str, date_to: str,
                        limit: int, api_key: str) -> list[str]:
    """分页拉取该药报告样本，本地统计出现频次最高的不良反应词（自动发现候选词）。"""
    from collections import Counter
    window = (f"receivedate:[{date_from.replace('-', '')} "
              f"TO {date_to.replace('-', '')}]")
    X = f"patient.drug.medicinalproduct:{drug.upper()}"
    search = f"({X})+AND+({window})"
    q = quote(search, safe=':+()"')

    counter: Counter = Counter()
    for page in range(SAMPLE_PAGES):
        skip = page * PER_PAGE
        # 小分页拉取：单条 ASPIRIN 记录很大，limit=100 单次 10MB+ 会被企业网络重置
        url = f"{API_BASE}?search={q}&limit={PER_PAGE}&skip={skip}"
        if api_key:
            url += f"&api_key={api_key}"
        try:
            r = requests.get(url, timeout=120)
            time.sleep(1.5)  # 匿名限速约 40 req/min，1.5s 间隔较安全
            if r.status_code == 429:
                time.sleep(5)
                continue
            r.raise_for_status()
            results = r.json().get("results", [])
            if not results:
                break
            for rec in results:
                for rxn in rec.get("patient", {}).get("reaction", []):
                    t = rxn.get("reactionmeddrapt")
                    if t:
                        counter[t] += 1
        except Exception as e:
            if page == 0:
                st.error(f"获取候选反应词失败：{e}")
            break   # 后续页失败则保留已有样本

    return [t for t, _ in counter.most_common(limit)]


def run_detection(drug, terms, date_from, date_to, api_key, progress_bar=None):
    """对候选词逐词做不成比例分析，返回 (df, N, countX)。带进度条。"""
    window = (f"receivedate:[{date_from.replace('-', '')} "
              f"TO {date_to.replace('-', '')}]")
    X = f"patient.drug.medicinalproduct:{drug.upper()}"

    N = cached_total(window, api_key)
    countX = cached_total(f"({X})+AND+({window})", api_key)

    rows = []
    total = len(terms)
    for i, term in enumerate(terms):
        Y = f'patient.reaction.reactionmeddrapt:"{term}"'
        countY = cached_total(f"({Y})+AND+({window})", api_key)
        countXY = cached_total(f"({X})+AND+({Y})+AND+({window})", api_key)

        a = countXY
        b = max(countX - a, 0)
        c = max(countY - a, 0)
        d = max(N - a - b - c, 0)

        m = fsd.disproportionality(a, b, c, d)
        f = fsd.signal_flags(a, m)
        row = {"reaction": term, "a": a, "b": b, "c": c, "d": d}
        row.update(m)
        row.update(f)
        rows.append(row)

        if progress_bar is not None:
            progress_bar.progress(
                (i + 1) / total,
                text=f"检索中 ({i + 1}/{total})：{term}",
            )

    df = pd.DataFrame(rows)
    df = df.sort_values(
        by=["IC", "ROR"], ascending=[False, False], na_position="last"
    ).reset_index(drop=True)
    return df, N, countX


def signal_color(strength: str) -> str:
    return {"强": "#d62728", "中": "#ff7f0e", "弱": "#f2c037", "-": "#9aa0a6"}.get(
        strength, "#9aa0a6"
    )


def make_chart(df: pd.DataFrame, metric: str, top_n: int):
    """画 Top 信号横向条形图（按所选指标排序）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plot_df = df.head(top_n).copy()
    plot_df = plot_df.sort_values(by=metric, ascending=True, na_position="first")

    fig, ax = plt.subplots(figsize=(9, max(3, 0.42 * len(plot_df) + 1)))
    colors = [signal_color(s) for s in plot_df["strength"]]
    ax.barh(plot_df["reaction"], plot_df[metric].fillna(0), color=colors)
    ax.set_xlabel(metric)
    ax.set_title(f"Top {len(plot_df)} 信号候选（{metric}）", fontsize=12)
    ax.axvline(1.0, color="#555", linestyle="--", linewidth=1)
    for i, (v, lo) in enumerate(zip(plot_df[metric], plot_df["ROR_low"])):
        if pd.notna(v):
            ax.text(v + 0.02, i, f"{v:.2f}", va="center", fontsize=8)
    plt.tight_layout()
    return fig


# --------------------------------------------------------------------------
# 本地模式：离线检测（带缓存，同参数重跑瞬时返回）
# --------------------------------------------------------------------------
@st.cache_data(ttl=7200, show_spinner=False)
def local_detect_cached(drug, data_dir, year_from, year_to, role_str, fuzzy, top):
    """离线扫描本地季度数据。返回 (df, N, countX, quarter_labels)。"""
    if not fls:
        return None, 0, 0, []
    quarters = fls.discover_quarters(data_dir, year_from, year_to)
    if not quarters:
        return None, 0, 0, []
    roles = (None if role_str.upper() == "ALL"
             else {r.strip().upper() for r in role_str.split(",")})
    df, N, countX = fls.detect(drug, quarters, roles, fuzzy, top, verbose=False)
    return df, N, countX, [q[0] for q in quarters]


# ==========================================================================
# Streamlit UI
# ==========================================================================
st.set_page_config(page_title="FAERS 药物安全信号检测", layout="wide")

st.title("FAERS 药物安全信号检测 Demo")
st.caption("输入药品通用名 → 实时不成比例分析（ROR / PRR / BCPNN-IC）→ Top 异常不良反应榜")

with st.sidebar:
    st.header("参数")

    # ---------- 数据来源 ----------
    if HAS_LOCAL:
        source = st.radio(
            "数据来源",
            ["本地 FAERS 数据(离线,推荐)", "在线 openFDA API"],
            index=0,
            help="本地模式直接读取本机季度原始数据，完全离线；在线模式需能访问 api.fda.gov",
        )
    else:
        source = "在线 openFDA API"
        st.caption("数据来源：在线 openFDA API（未检测到本地数据模块）")

    drug = st.text_input("药品通用名", value="ASPIRIN",
                         help="英文通用名，如 ASPIRIN / METFORMIN / IBUPROFEN")

    # 本地分支控件
    loc_dir = fls.DEFAULT_DATA_DIR if fls else ""
    loc_year_from, loc_year_to = 2022, 2025
    loc_role, loc_fuzzy = "ALL", False
    # 在线分支控件（占位，避免未定义）
    date_from = pd.to_datetime("2022-01-01")
    date_to = pd.to_datetime("2026-12-31")
    mode, top_terms, csv_top = "自动发现(推荐)", 25, 25
    csv_file, manual = None, ""

    if source.startswith("本地"):
        st.markdown("---")
        st.subheader("本地数据设置")
        loc_dir = st.text_input("季度 zip 目录", value=loc_dir)
        y1, y2 = st.columns(2)
        with y1:
            loc_year_from = int(st.number_input("起始年份", 2018, 2030, 2022))
        with y2:
            loc_year_to = int(st.number_input("截止年份", 2018, 2030, 2025))
        loc_role = st.selectbox(
            "用药角色", ["ALL", "PS", "SS", "C", "I", "PS,SS"], index=0,
            help="PS=首要怀疑 SS=次要怀疑 C=并用 I=相互作用")
        loc_fuzzy = st.checkbox(
            "药名模糊匹配(子串)", value=False,
            help="勾选后可覆盖 ASPIRIN 81MG、BAYER ASPIRIN 等变体写法")
        top_terms = st.slider("输出 Top-N 信号", 5, 60, 25)
    else:
        col1, col2 = st.columns(2)
        with col1:
            date_from = st.date_input("起始日期", value=pd.to_datetime("2022-01-01"))
        with col2:
            date_to = st.date_input("截止日期", value=pd.to_datetime("2026-12-31"))

        mode = st.radio("候选反应词来源", ["自动发现(推荐)", "从 CSV 提取", "手动输入"])
        if mode == "自动发现(推荐)":
            top_terms = st.slider("自动取 Top-N 反应词", 5, 40, 20)
        elif mode == "从 CSV 提取":
            csv_file = st.file_uploader("上传 ingest 产出的 CSV", type=["csv"])
            csv_top = st.slider("提取前 N 个反应词", 5, 60, 25)
        else:
            manual = st.text_area("候选反应词（逗号/分号分隔）",
                                  "Chest pain; Headache; Nausea; Gastric haemorrhage")
            top_terms = 25

    metric = st.selectbox("图表排序指标", ["IC", "ROR", "PRR"], index=0)
    chart_top = st.slider("图表显示条数", 5, 40, 15)
    api_key = st.text_input("openFDA API Key（可选，提速）", type="password")
    run = st.button("开始检测", type="primary", use_container_width=True)

# 主流程
if run and drug.strip():
    drug = drug.strip()

    if source.startswith("本地") and fls:
        # ---------------- 本地模式（离线读取季度原始数据） ----------------
        with st.spinner(
            f"扫描本地数据（{loc_year_from}–{loc_year_to}，约需 1-5 分钟）…"
        ):
            df, N, countX, qlabels = local_detect_cached(
                drug, loc_dir, loc_year_from, loc_year_to,
                loc_role, loc_fuzzy, top_terms
            )
        if df is None or df.empty:
            if df is None:
                st.error(f"在目录「{loc_dir}」未找到 faers_ascii_*.zip，请检查路径。")
            else:
                st.error("未匹配到该药品的用药记录。请确认药名拼写，或勾选「药名模糊匹配」。")
            st.stop()
        st.success(
            f"本地扫描完成：{qlabels[0]}~{qlabels[-1]}，共 {N:,} 份报告，"
            f"其中含 {drug.upper()} 的报告 {countX:,} 份。"
        )
    else:
        # ---------------- 在线模式（openFDA API） ----------------
        df_from, dt_to = str(date_from), str(date_to)
        terms = []
        with st.spinner("准备候选反应词…"):
            if mode == "自动发现(推荐)":
                terms = fetch_top_reactions(drug, df_from, dt_to, top_terms, api_key)
                if not terms:
                    st.error("未取到候选反应词，请检查药名或时间窗。")
                    st.stop()
                st.info(f"自动发现 {len(terms)} 个高频反应词。")
            elif mode == "从 CSV 提取":
                if not csv_file:
                    st.error("请先上传 CSV 文件。")
                    st.stop()
                import tempfile
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
                tmp.write(csv_file.read())
                tmp.close()
                terms = fsd.candidates_from_csv(tmp.name, csv_top)
                os.unlink(tmp.name)
            else:
                terms = fsd.parse_reactions(manual)

        progress = st.progress(0.0, text="准备检索…")
        df, N, countX = run_detection(
            drug, terms, df_from, dt_to, api_key, progress_bar=progress
        )
        progress.empty()

    # 结果写入 session_state，保证后续调整图表/排序时结果不丢失
    st.session_state["result"] = (df, N, countX, drug.upper())

elif run and not drug.strip():
    st.warning("请输入药品通用名。")

# =====================================================================
# 结果展示（从 session_state 读取，跨重跑保持）
# =====================================================================
if "result" in st.session_state:
    df, N, countX, drug_label = st.session_state["result"]

    # 3) 概览指标
    st.subheader(f"{drug_label} · 安全信号总览")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("时间窗内总报告", f"{N:,}")
    c2.metric(f"含 {drug_label} 报告", f"{countX:,}")
    c3.metric("判定为信号", f"{int(df['is_signal'].sum())}/{len(df)}")
    c4.metric("强 / 中 / 弱",
              f"{int((df['strength']=='强').sum())} / "
              f"{int((df['strength']=='中').sum())} / "
              f"{int((df['strength']=='弱').sum())}")

    # 4) Top 信号榜（图表）
    st.subheader(f"Top {chart_top} 信号候选（按 {metric}）")
    fig = make_chart(df, metric, chart_top)
    st.pyplot(fig)

    # 5) 明细表
    st.subheader("明细（按 IC 降序）")
    show_cols = ["reaction", "a", "ROR", "ROR_low", "PRR", "PRR_chi2",
                 "IC", "IC025", "strength", "n_signals"]
    table_df = df[show_cols].copy()

    def highlight(row):
        c = signal_color(row["strength"])
        return [f"background-color: {c}22; color: #222;" for _ in row]

    styled = table_df.style.apply(highlight, axis=1).format(
        {"ROR": "{:.2f}", "ROR_low": "{:.2f}", "PRR": "{:.2f}",
         "PRR_chi2": "{:.1f}", "IC": "{:.2f}", "IC025": "{:.2f}"}
    )
    st.dataframe(styled, use_container_width=True, height=520)

    # 6) 下载
    out_name = f"signals_{drug_label.lower().replace(' ', '_')}.csv"
    st.download_button("下载完整结果 CSV",
                       df.to_csv(index=False, encoding="utf-8-sig"),
                       file_name=out_name, mime="text/csv")

# 方法学与免责声明
with st.expander("方法学说明 / 免责声明"):
    st.markdown("""
    **不成比例分析（Disproportionality Analysis）** 是药物警戒中从自发报告库挖掘安全信号的经典方法。
    对「药物 X 与反应 Y」构造 2×2 列联表，比较 Y 在「用 X 的报告」与「不用 X 的报告」中出现频率的偏离程度：

    | 指标 | 公式要点 | 信号标准 |
    |---|---|---|
    | ROR | (a·d)/(b·c) | a≥3 且 95%CI 下限 > 1 |
    | PRR | [a/(a+b)]/[c/(c+d)] | a≥3 且 PRR≥2 且 χ²≥4 |
    | IC (BCPNN) | 贝叶斯信息分量 | IC025 > 0 |

    - 数据来源：FDA openFDA `drug/event.json`（公开、免 key，匿名约 40 次/分钟）。
    - 本 Demo 仅用于方法学演示与 AI 作品集，**不构成医疗建议或监管结论**。
    """)
