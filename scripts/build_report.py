#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 FAERS 信号检测的多品种 CSV 汇总成 Markdown 月报，并写一份 JSON 侧车
（记录各品种强信号列表），供下月运行时对比「新出现的强信号」。

纯标准库实现，CI 中无需额外依赖。

用法：
    python scripts/build_report.py --in-dir artifacts --out-dir reports
其中 artifacts/ 下每个子目录含一个 signals_<DRUG>.csv（由 download-artifact 产出）。
"""
import argparse
import csv
import glob
import json
import os
from datetime import date, timedelta

STRONG, MID, WEAK = "强", "中", "弱"


def prev_month_ym() -> str:
    d = date.today().replace(day=1) - timedelta(days=1)
    return d.strftime("%Y-%m")


def drug_from_path(p: str) -> str:
    base = os.path.basename(p)
    if base.startswith("signals_") and base.endswith(".csv"):
        return base[len("signals_"):-len(".csv")]
    return base


def fmt_range(v, lo, hi=None):
    """把数值格式化为 `值 (下限–上限)`；仅给下限时输出 `值 (下限)`。"""
    if v in (None, ""):
        return "—"
    s = str(v)
    if lo not in (None, "") and hi not in (None, ""):
        s += f" ({lo}–{hi})"
    elif lo not in (None, ""):
        s += f" ({lo})"
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", required=True, help="含 signals_*.csv 的目录（可含子目录）")
    ap.add_argument("--out-dir", required=True, help="月报输出目录（如 reports/）")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    ym = date.today().strftime("%Y-%m")
    prev = prev_month_ym()

    paths = sorted(glob.glob(os.path.join(args.in_dir, "**", "signals_*.csv"), recursive=True))
    drugs = {}
    for p in paths:
        drug = drug_from_path(p)
        with open(p, encoding="utf-8-sig", newline="") as f:
            drugs[drug] = list(csv.DictReader(f))

    if not drugs:
        print("⚠ 未发现任何 signals_*.csv，跳过月报生成。")
        return

    # 上月 JSON 侧车（首月不存在则跳过对比）
    prev_json = {}
    pj = os.path.join(args.out_dir, f"signals-report-{prev}.json")
    if os.path.exists(pj):
        try:
            prev_json = json.load(open(pj, encoding="utf-8"))
        except Exception:
            prev_json = {}

    overview, new_strong, detail_blocks, json_out = [], {}, [], {}

    for drug in sorted(drugs):
        rows = drugs[drug]
        n_strong = sum(1 for r in rows if r.get("strength") == STRONG)
        n_mid = sum(1 for r in rows if r.get("strength") == MID)
        n_weak = sum(1 for r in rows if r.get("strength") == WEAK)
        overview.append((drug, n_strong, n_mid, n_weak, len(rows)))

        cur_strong = [r["reaction"] for r in rows if r.get("strength") == STRONG]
        json_out[drug] = cur_strong
        prev_strong = set(prev_json.get(drug, []))
        ns = [r for r in cur_strong if r not in prev_strong]
        if ns:
            new_strong[drug] = ns

        lines = [f"### {drug}", "",
                 "Top 信号（按 IC 降序，显示前 10）：", "",
                 "| 不良反应 | ROR (95%CI) | PRR | IC (IC025) | 强度 |",
                 "|----------|-------------|-----|------------|------|"]
        for r in rows[:10]:
            ror = fmt_range(r.get("ROR"), r.get("ROR_low"), r.get("ROR_high"))
            ic = fmt_range(r.get("IC"), r.get("IC025"))
            lines.append(f"| {r.get('reaction','')} | {ror} | {r.get('PRR','') or '—'} | {ic} | {r.get('strength','')} |")
        if len(rows) > 10:
            lines.append("")
            lines.append(f"_（共 {len(rows)} 条，完整结果见 artifact `signals_{drug}.csv`）_")
        lines.append("")
        detail_blocks.append("\n".join(lines))

    md = []
    md.append(f"# FAERS 信号检测月报 — {ym}\n")
    md.append(f"- 生成日期：{date.today().isoformat()}")
    md.append(f"- 数据来源：FDA openFDA（公开、免费）")
    md.append(f"- 方法：ROR / PRR / BCPNN-IC 不成比例分析")
    md.append(f"- 监测品种：{', '.join(sorted(drugs))}\n")
    md.append("## 总览\n")
    md.append("| 品种 | 强信号 | 中信号 | 弱信号 | 信号总数 |")
    md.append("|------|--------|--------|--------|----------|")
    for d, s, m, w, t in overview:
        md.append(f"| {d} | {s} | {m} | {w} | {t} |")
    md.append("")

    md.append("## ⚠ 新强信号（较上月）\n")
    if new_strong:
        for d, lst in new_strong.items():
            for rct in lst:
                md.append(f"- **{d}**：{rct}（上月未出现）")
    else:
        md.append("本月无新强信号（或为首月运行）。")
    md.append("")

    md.append("## 各品种明细\n")
    md.append("\n".join(detail_blocks))

    md.append("\n---\n")
    md.append("_本报表由 GitHub Actions 自动生成，基于 FDA openFDA 公开数据；信号仅提示关联、"
              "不能证明因果，须由 qualified person 在 PV QMS 内判读。_\n")

    md_path = os.path.join(args.out_dir, f"signals-report-{ym}.md")
    json_path = os.path.join(args.out_dir, f"signals-report-{ym}.json")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_out, f, ensure_ascii=False, indent=2)

    print(f"✓ 月报已生成：{md_path}")
    print(f"✓ 机器侧车：{json_path}")
    for d, s, m, w, t in overview:
        print(f"  {d}: 强 {s} / 中 {m} / 弱 {w} / 共 {t}")


if __name__ == "__main__":
    main()
