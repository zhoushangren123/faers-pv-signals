#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAERS 本地信号检测 · 独立离线版
================================
一个完全离线运行的桌面小工具：选择本机任意 FAERS/AERS 季度数据文件夹，
输入药品名，即输出该药的 Top 异常不良反应榜（ROR / PRR / BCPNN-IC）。

与在线版(streamlit_faers_app.py)的区别：
  - 数据来源是本机的官方季度原始 zip，**全程零联网**
  - 可自由切换数据文件夹（支持「自动查找」扫描各盘符）
  - 支持 2004 年起的 AERS 旧数据（字段按表头名动态定位，兼容无 prod_ai 的早期格式）

运行：
  streamlit run faers_local_app.py
依赖：streamlit pandas matplotlib
"""

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import faers_local_signals as fls  # noqa: E402
import faers_signal_detection as fsd  # noqa: E402

st.set_page_config(page_title="FAERS 本地信号检测", page_icon="💊",
                   layout="wide")

st.title("💊 FAERS 本地信号检测（离线版）")
st.caption("直接读取本机 FAERS/AERS 季度原始数据做不成比例分析（ROR / PRR / BCPNN-IC），全程无需联网")

# ---------------------------------------------------------------- 状态初始化
for k, v in (("data_dir", fls.DEFAULT_DATA_DIR), ("cands", None),
             ("result", None), ("scanned", False)):
    if k not in st.session_state:
        st.session_state[k] = v


def signal_color(s: str) -> str:
    return {"强": "#d62728", "中": "#ff7f0e", "弱": "#f2c037",
            "-": "#9aa0a6"}.get(s, "#9aa0a6")


def make_chart(df, metric, top_n):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei",
                                       "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    d = df.head(top_n).sort_values(by=metric, ascending=True,
                                   na_position="first")
    fig, ax = plt.subplots(figsize=(9, max(3, 0.42 * len(d) + 1)))
    ax.barh(d["reaction"], d[metric].fillna(0),
            color=[signal_color(s) for s in d["strength"]])
    ax.set_xlabel(metric)
    ax.set_title(f"Top {len(d)} 信号候选（按 {metric}）", fontsize=12)
    ax.axvline(1.0, color="#555", linestyle="--", linewidth=1)
    for i, v in enumerate(d[metric]):
        if pd.notna(v):
            ax.text(v + 0.02, i, f"{v:.2f}", va="center", fontsize=8)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------- 侧栏
with st.sidebar:
    st.header("① 数据文件夹")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔍 自动查找", use_container_width=True,
                     help="扫描 C~J 盘，找出含 FAERS 季度 zip 的文件夹"):
            with st.spinner("正在扫描各盘符…（约十几秒）"):
                try:
                    st.session_state["cands"] = fls.scan_candidate_dirs()
                    st.session_state["scanned"] = True
                except Exception as e:
                    st.error(f"扫描失败：{e}")
    with c2:
        if st.button("↺ 清空结果", use_container_width=True):
            st.session_state["cands"] = None
            st.session_state["scanned"] = False

    cands = st.session_state.get("cands")
    if cands:
        labels = [f"{p}　|　{n} 个季度（{a} ~ {b}）" for p, n, a, b in cands]
        cur = st.session_state.get("data_dir", "")
        idx = next((i for i, c in enumerate(cands) if c[0] == cur), 0)
        chosen = st.selectbox("已找到的数据目录（可切换）", labels, index=idx)
        if chosen:
            st.session_state["data_dir"] = chosen.split("　|　")[0]
    elif st.session_state.get("scanned"):
        st.info("未扫描到数据目录，请用下方输入框手动填写路径。")

    data_dir = st.text_input(
        "数据目录", key="data_dir",
        help="也可从资源管理器地址栏复制路径粘贴到这里，例如 F:\\郑州大学\\fares数据-2018-2025")

    quarters_all = []
    if data_dir:
        try:
            quarters_all = fls.discover_quarters(data_dir)
        except Exception:
            quarters_all = []

    if quarters_all:
        labels_q = [q[0] for q in quarters_all]
        years = sorted({int(x[:4]) for x in labels_q})
        y_min, y_max = years[0], years[-1]
        st.success(f"✅ 发现 {len(labels_q)} 个季度：{labels_q[0]} ~ {labels_q[-1]}")
    else:
        st.warning("该目录下未找到 faers_ascii_*.zip / aers_ascii_*.zip")
        y_min, y_max = 2018, 2025

    st.markdown("---")
    st.header("② 检测参数")

    nf, nt = st.columns(2)
    with nf:
        year_from = int(st.number_input("起始年", 1990, 2035, y_min))
    with nt:
        year_to = int(st.number_input("截止年", 1990, 2035, y_max))
    if year_from > year_to:
        st.error("起始年不能大于截止年")

    drug = st.text_input("药品通用名", value="ASPIRIN",
                         help="英文通用名，如 ASPIRIN / METFORMIN / IBUPROFEN")

    role = st.selectbox("用药角色", ["ALL", "PS", "SS", "C", "I", "PS,SS"],
                        index=0,
                        help="PS=首要怀疑 SS=次要怀疑 C=并用 I=相互作用；"
                             "做严谨分析建议选 PS")
    fuzzy = st.checkbox("药名模糊匹配（子串）", value=False,
                        help="覆盖 'ASPIRIN 81MG'、'BAYER ASPIRIN' 等变体写法")
    top_n = st.slider("输出 Top-N 信号", 5, 100, 25)
    run = st.button("🚀 开始检测", type="primary", use_container_width=True)

    st.markdown("---")
    metric = st.selectbox("图表排序指标", ["IC", "ROR", "PRR"], index=0)
    chart_top = st.slider("图表显示条数", 5, 60, 20)


# ---------------------------------------------------------------- 执行检测
def do_run():
    quarters = fls.discover_quarters(data_dir, year_from, year_to)
    if not quarters:
        st.error("所选年份范围内没有可用的季度数据，请调整年份或换目录。")
        return
    roles = (None if role.upper() == "ALL"
             else {r.strip().upper() for r in role.split(",")})

    prog = st.progress(0.0, text="准备扫描…")
    status = st.empty()

    def cb(label, i, total):
        prog.progress(i / total, text=f"处理中 {i + 1}/{total}：{label}")
        status.caption(f"正在读取 **{label}**（第 {i + 1}/{total} 个季度）…")

    try:
        df, N, countX = fls.detect(drug, quarters, roles, fuzzy, top_n,
                                   verbose=False, on_quarter=cb)
    except Exception as e:
        prog.empty()
        status.empty()
        st.error(f"检测失败：{type(e).__name__}: {e}")
        return
    prog.progress(1.0, text="扫描完成")
    prog.empty()
    status.empty()

    if df.empty:
        st.warning("未匹配到该药品的用药记录。请确认药名拼写，或勾选「药名模糊匹配」。")
        return

    st.session_state["result"] = (
        df, N, countX, drug.upper(),
        [q[0] for q in quarters], role, fuzzy,
    )


if run:
    if not drug.strip():
        st.warning("请输入药品通用名。")
    else:
        do_run()


# ---------------------------------------------------------------- 结果展示
res = st.session_state.get("result")
if res:
    df, N, countX, drug_label, qlabels, role_used, fuzzy_used = res

    st.success(
        f"✅ **{drug_label}**　|　{qlabels[0]} ~ {qlabels[-1]}　|　"
        f"角色={role_used}{'　|　模糊匹配' if fuzzy_used else ''}　|　"
        f"共 {N:,} 份报告，其中 {countX:,} 份含该药"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("报告总数", f"{N:,}")
    c2.metric(f"含 {drug_label}", f"{countX:,}")
    c3.metric("判定为信号", f"{int(df['is_signal'].sum())}/{len(df)}")
    c4.metric("强 / 中 / 弱",
              f"{int((df['strength'] == '强').sum())} / "
              f"{int((df['strength'] == '中').sum())} / "
              f"{int((df['strength'] == '弱').sum())}")

    st.subheader(f"Top {chart_top} 信号候选（按 {metric}）")
    st.pyplot(make_chart(df, metric, chart_top))

    st.subheader("明细（按 IC 降序）")
    show = ["reaction", "a", "ROR", "ROR_low", "PRR", "PRR_chi2",
            "IC", "IC025", "strength", "n_signals"]
    tbl = df[show].copy()

    def hl(row):
        return [f"background-color: {signal_color(row['strength'])}22; "
                f"color: #222;" for _ in row]

    styled = tbl.style.apply(hl, axis=1).format(
        {"ROR": "{:.2f}", "ROR_low": "{:.2f}", "PRR": "{:.2f}",
         "PRR_chi2": "{:.1f}", "IC": "{:.2f}", "IC025": "{:.2f}"}
    )
    st.dataframe(styled, use_container_width=True, height=520)

    st.download_button(
        "⬇️ 下载完整结果 CSV",
        df.to_csv(index=False, encoding="utf-8-sig"),
        file_name=f"signals_{drug_label.lower().replace(' ', '_')}"
                  f"_{qlabels[0]}_{qlabels[-1]}.csv",
        mime="text/csv",
    )
else:
    st.info(
        "左侧选择数据文件夹 → 填药品名 → 点「🚀 开始检测」。\n\n"
        "首次扫描某个年份范围可能需要几分钟（数据量大），"
        "之后切换图表排序是瞬时的。"
    )

# ---------------------------------------------------------------- 导出原始病例
APP_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(APP_DIR, "exports")

st.markdown("---")
st.subheader("📦 导出原始病例数据")
st.caption(
    "把「含该药的全部报告」导出成**病例级明细 CSV**："
    "人口学（年龄/性别/体重/国家/事件日期）+ 用药（名称/角色/给药途径）+ "
    "不良反应（全部 PT）+ 结局（是否严重）。可直接用 Excel 打开做二次分析。"
)

if st.button("⬇️ 导出病例数据", key="btn_export"):
    if not drug.strip():
        st.warning("请先填写药品通用名。")
    else:
        quarters = fls.discover_quarters(data_dir, year_from, year_to)
        if not quarters:
            st.error("所选年份范围内没有可用的季度数据。")
        else:
            roles = (None if role.upper() == "ALL"
                     else {r.strip().upper() for r in role.split(",")})
            prog = st.progress(0.0, text="准备导出…")
            status = st.empty()

            def cb2(label, i, total):
                prog.progress(i / total, text=f"导出中 {i + 1}/{total}：{label}")
                status.caption(f"正在读取 **{label}**（第 {i + 1}/{total} 个季度）…")

            cdf = None
            try:
                cdf, cN, cX = fls.extract_cases(
                    quarters, drug.strip().upper(), roles, fuzzy,
                    verbose=False, on_quarter=cb2)
            except Exception as e:
                st.error(f"导出失败：{type(e).__name__}: {e}")
            finally:
                prog.empty()
                status.empty()

            if cdf is not None:
                if cdf.empty:
                    st.warning("未匹配到该药品的病例。请确认药名拼写，或勾选「药名模糊匹配」。")
                else:
                    os.makedirs(EXPORT_DIR, exist_ok=True)
                    safe = drug.strip().upper().replace(" ", "_")
                    fname = f"cases_{safe}_{year_from}_{year_to}.csv"
                    fpath = os.path.join(EXPORT_DIR, fname)
                    cdf.to_csv(fpath, index=False, encoding="utf-8-sig")
                    size_mb = os.path.getsize(fpath) / 1024 / 1024

                    st.success(
                        f"✅ 已导出 **{len(cdf):,} 条病例**"
                        f"（时间窗内共 {cN:,} 份报告，含该药 {cX:,} 份）"
                        f"　·　{size_mb:.1f} MB\n\n"
                        f"文件已保存到：`{fpath}`"
                    )
                    st.dataframe(cdf.head(20), use_container_width=True)
                    st.download_button(
                        "⬇️ 下载该 CSV",
                        cdf.to_csv(index=False, encoding="utf-8-sig"),
                        file_name=fname, mime="text/csv",
                    )

# ---------------------------------------------------------------- 说明
with st.expander("方法学说明 / 使用提示 / 免责声明"):
    st.markdown("""
    **不成比例分析（Disproportionality Analysis）** 是药物警戒中从自发报告库
    挖掘安全信号的经典方法。对「药物 X 与反应 Y」构造 2×2 列联表，比较 Y 在
    「用 X 的报告」与「不用 X 的报告」中出现频率的偏离程度。

    | 指标 | 公式要点 | 信号标准 |
    |---|---|---|
    | ROR | (a·d)/(b·c) | a≥3 且 95%CI 下限 > 1 |
    | PRR | [a/(a+b)]/[c/(c+d)] | a≥3 且 PRR≥2 且 χ²≥4 |
    | IC (BCPNN) | 贝叶斯信息分量 | IC025 > 0 |

    **使用提示**
    - 数据来源：FDA 官方 FAERS/AERS 季度 ASCII 原始数据（本机目录，`$` 分隔）。
    - 「用药角色」选 **PS（首要怀疑药）** 结果更严谨；ALL 会混入并用药物。
    - 药名匹配不到时（如 ASPIRIN 写成了 BAYER ASPIRIN），勾选「模糊匹配」。
    - 年份范围越大越慢；先用 2–3 年试跑，确认无误再扩到全量。

    **重要局限（解读结果时务必注意）**
    - 自发报告存在**适应症混杂**：老年人常用药的 Top 信号常出现
      Pneumonia、Fall、Arthritis 等基础疾病/合并用药相关事件，
      **不代表药物导致这些事件**。
    - 报告数多不等于风险高；信号只是"值得进一步评估"的线索，
      需结合临床、文献、流行病学数据综合判断。
    - 本工具仅用于方法学演示与内部参考，**不构成医疗建议或监管结论**。
    """)
