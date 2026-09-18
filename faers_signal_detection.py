#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAERS 信号检测模块（ROR / PRR 不成比例分析）
============================================
用途：给定一种药物，从 FDA 公开不良反应库(openFDA)中，对其报告的各类不良反应
      做「不成比例分析(disproportionality analysis)」，输出该药
      **Top 异常不良反应榜**（即潜在安全信号）。

方法学（药物警戒标准三件套）：
  - ROR   报告比值比 (Reporting Odds Ratio)
  - PRR   比例报告比 (Proportional Reporting Ratio) + χ²
  - BCPNN IC  贝叶斯置信传播神经网络信息分量 (Information Component)
  三者互为印证，任一达标即视为「信号」；越强则越多指标同时达标。

与取数脚本的衔接：
  - 本模块可直接读取 `faers_openfda_ingest.py` 产出的 CSV（--csv），
    从中按出现频次提取该药「最常报告的不良反应」作为候选词，
    再对每个候选词在 openFDA 上算四格表。无需下载全量数据。

接口 / 限速（同取数脚本）：
  - https://api.fda.gov/drug/event.json  免费、免 key
  - 匿名约 40 req/min；填 --api_key 可放宽到约 240 req/min
  - ⚠ 关键坑（实测）：必须用 urllib.parse.quote(search, safe=':+()"')
    手工拼 URL；若把 search 交给 requests 的 params= 会自动转义掉
    `+`(AND) 和 `:`，导致查询失效 / 数字错乱。

环境：pip install requests pandas
运行示例：
  # 用取数脚本产出的 CSV 自动提候选词
  python faers_signal_detection.py --drug ASPIRIN --csv faers_aspirin.csv --top_terms 25
  # 或显式指定候选反应词（便于快速验证）
  python faers_signal_detection.py --drug ASPIRIN --reactions "Gastric haemorrhage;Headache;Nausea"
"""

import argparse
import math
import sys
import time
from functools import lru_cache

import pandas as pd
import requests
from urllib.parse import quote

API_BASE = "https://api.fda.gov/drug/event.json"
REQUEST_DELAY = 0.3          # 每次 API 调用后间隔(秒)；有 key 可降到 0.05
API_KEY = ""                 # 可选：填上免费 key 提升限速


# --------------------------------------------------------------------------
# 1) API 计数（返回符合 search 的报告总数）
# --------------------------------------------------------------------------
def api_total(search: str, api_key: str = API_KEY, delay: float = REQUEST_DELAY) -> int:
    """返回符合 search 条件的报告总数（用 meta.results.total）。

    必须用 quote(safe=':+()"') 保留 openFDA 搜索语法字符，否则 +/: 被转义。
    """
    q = quote(search, safe=':+()"')
    url = f"{API_BASE}?search={q}&limit=0"
    if api_key:
        url += f"&api_key={api_key}"

    for attempt in range(4):
        try:
            r = requests.get(url, timeout=90)
            if r.status_code == 429:           # 触发限速，退避重试
                time.sleep(5 + attempt * 5)
                continue
            r.raise_for_status()
            total = r.json()["meta"]["results"]["total"]
            time.sleep(delay)
            return int(total)
        except Exception as e:
            if attempt == 3:
                raise RuntimeError(f"API 失败: {search} -> {e}")
            time.sleep(3 + attempt * 2)
    return 0


# --------------------------------------------------------------------------
# 2) 不成比例分析核心公式
# --------------------------------------------------------------------------
def disproportionality(a: int, b: int, c: int, d: int) -> dict:
    """由 2×2 列联表计算 ROR / PRR / χ² / IC 及其 95% 置信区间。

        反应 Y      非 Y
    药 X     a         b
    非 X     c         d

    返回 dict；若 a=0 或分母含 0，对应指标置为 None。
    """
    N = a + b + c + d
    out = {"a": a, "b": b, "c": c, "d": d, "N": N}

    if a == 0 or min(b, c, d) <= 0:
        out.update({
            "ROR": None, "ROR_low": None, "ROR_high": None,
            "PRR": None, "PRR_low": None, "PRR_high": None, "PRR_chi2": None,
            "IC": None, "IC025": None,
        })
        return out

    # ---- ROR ----
    ror = (a * d) / (b * c)
    se_ror = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    ror_low = math.exp(math.log(ror) - 1.96 * se_ror)
    ror_high = math.exp(math.log(ror) + 1.96 * se_ror)

    # ---- PRR ----
    prr = (a / (a + b)) / (c / (c + d))
    se_prr = math.sqrt(1 / a - 1 / (a + b) + 1 / c - 1 / (c + d))
    prr_low = math.exp(math.log(prr) - 1.96 * se_prr)
    prr_high = math.exp(math.log(prr) + 1.96 * se_prr)
    # 2×2 Pearson χ²（无连续性校正，药物警戒惯例）
    chi2 = (N * (a * d - b * c) ** 2) / ((a + b) * (c + d) * (a + c) * (b + d))

    # ---- BCPNN IC ----
    alpha = 0.5
    ic = math.log2((a + alpha) * (N + alpha) / ((a + b + alpha) * (a + c + alpha)))
    se_ic = math.sqrt(1 / (a + alpha) + 1 / (a + b + alpha)
                      + 1 / (a + c + alpha) - 1 / (N + alpha))
    ic025 = ic - 1.96 * se_ic

    out.update({
        "ROR": round(ror, 3), "ROR_low": round(ror_low, 3), "ROR_high": round(ror_high, 3),
        "PRR": round(prr, 3), "PRR_low": round(prr_low, 3), "PRR_high": round(prr_high, 3),
        "PRR_chi2": round(chi2, 2),
        "IC": round(ic, 3), "IC025": round(ic025, 3),
    })
    return out


def signal_flags(a: int, m: dict) -> dict:
    """按国际通行信号标准打标。"""
    ror_sig = bool(a >= 3 and m["ROR_low"] is not None and m["ROR_low"] > 1)
    prr_sig = bool(a >= 3 and m["PRR"] is not None and m["PRR"] >= 2
                   and m["PRR_chi2"] is not None and m["PRR_chi2"] >= 4)
    ic_sig = bool(m["IC025"] is not None and m["IC025"] > 0)
    n_sig = sum([ror_sig, prr_sig, ic_sig])
    return {
        "is_ror_signal": ror_sig,
        "is_prr_signal": prr_sig,
        "is_bcpnn_signal": ic_sig,
        "n_signals": n_sig,
        "is_signal": n_sig >= 1,
        # 强度分级：3 项全中=强信号；2 项=中等；1 项=弱
        "strength": {3: "强", 2: "中", 1: "弱", 0: "-"}[n_sig],
    }


# --------------------------------------------------------------------------
# 3) 信号检测器
# --------------------------------------------------------------------------
class SignalDetector:
    def __init__(self, drug: str, date_from: str, date_to: str,
                 api_key: str = API_KEY, delay: float = REQUEST_DELAY):
        self.drug = drug.upper()
        self.X = f"patient.drug.medicinalproduct:{self.drug}"
        self.window = f"receivedate:[{date_from.replace('-', '')} TO {date_to.replace('-', '')}]"
        self.api_key = api_key
        self.delay = delay
        self._cache: dict[str, int] = {}

    def _wrap(self, sub: str) -> str:
        """把子查询套进时间窗：(sub)+AND+(window)"""
        return f"({sub})+AND+({self.window})"

    def _count(self, search: str) -> int:
        if search in self._cache:
            return self._cache[search]
        v = api_total(search, self.api_key, self.delay)
        self._cache[search] = v
        return v

    def baseline(self) -> tuple[int, int]:
        """返回 (N 时间窗内总报告数, 含该药报告数 a+b)。"""
        N = self._count(self.window)
        countX = self._count(self._wrap(self.X))
        return N, countX

    def detect_term(self, term: str, N: int, countX: int) -> dict:
        """对单个反应词做不成比例分析，返回完整一行。"""
        Y = f'patient.reaction.reactionmeddrapt:"{term}"'
        countY = self._count(self._wrap(Y))              # a + c
        countXY = self._count(self._wrap(f"{self.X}+AND+{Y}"))  # a

        a = countXY
        b = max(countX - a, 0)
        c = max(countY - a, 0)
        d = max(N - a - b - c, 0)

        m = disproportionality(a, b, c, d)
        f = signal_flags(a, m)
        row = {"reaction": term, "a": a, "b": b, "c": c, "d": d}
        row.update(m)
        row.update(f)
        return row

    def detect(self, terms: list[str], N: int, countX: int) -> pd.DataFrame:
        rows = [self.detect_term(t, N, countX) for t in terms]
        df = pd.DataFrame(rows)
        # 排序：先按 IC 降序（IC 缺失排最后），再按 ROR 降序
        df = df.sort_values(
            by=["IC", "ROR"], ascending=[False, False], na_position="last"
        ).reset_index(drop=True)
        return df


# --------------------------------------------------------------------------
# 4) 候选反应词来源
# --------------------------------------------------------------------------
def candidates_from_csv(csv_path: str, top_n: int) -> list[str]:
    """从取数脚本产出的 CSV 中，按出现频次提取 Top-N 反应词。"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    if "reactions" not in df.columns:
        raise ValueError("CSV 中未见 'reactions' 列，请确认由 faers_openfda_ingest.py 产出。")
    terms = []
    for cell in df["reactions"].dropna():
        for t in str(cell).split("; "):
            t = t.strip()
            if t:
                terms.append(t)
    vc = pd.Series(terms).value_counts()
    return vc.head(top_n).index.tolist()


def parse_reactions(text: str) -> list[str]:
    """把 'A;B,C' 这类字符串解析为词列表。"""
    out = []
    for part in text.replace(";", ",").split(","):
        p = part.strip()
        if p:
            out.append(p)
    return out


# --------------------------------------------------------------------------
# 5) 主流程
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="FAERS 信号检测（ROR/PRR/BCPNN 不成比例分析）")
    parser.add_argument("--drug", default="ASPIRIN", help="药品通用名(大写匹配)")
    parser.add_argument("--csv", default=None, help="取数脚本产出的 CSV，自动提取候选反应词")
    parser.add_argument("--reactions", default=None, help="显式候选反应词，逗号/分号分隔")
    parser.add_argument("--top_terms", type=int, default=15, help="从 CSV 提取的候选词数量")
    parser.add_argument("--date_from", default="2022-01-01", help="时间窗起点")
    parser.add_argument("--date_to", default="2026-12-31", help="时间窗终点")
    parser.add_argument("--top_signals", type=int, default=20, help="输出 Top 信号条数")
    parser.add_argument("--out", default=None, help="输出 CSV 路径")
    parser.add_argument("--api_key", default=API_KEY, help="openFDA 免费 key(可选)")
    args = parser.parse_args()

    # 决定候选反应词
    if args.csv:
        print(f"▶ 从 {args.csv} 提取 Top-{args.top_terms} 反应词…")
        terms = candidates_from_csv(args.csv, args.top_terms)
    elif args.reactions:
        terms = parse_reactions(args.reactions)
    else:
        sys.exit("✗ 请通过 --csv 或 --reactions 提供候选反应词。")

    if not terms:
        sys.exit("✗ 未获得任何候选反应词，请检查 CSV 或 --reactions。")

    print(f"▶ 药物: {args.drug}  候选反应词: {len(terms)}  窗口: {args.date_from}~{args.date_to}")

    det = SignalDetector(args.drug, args.date_from, args.date_to, args.api_key)
    N, countX = det.baseline()
    print(f"  时间窗内总报告 N = {N:,}；含 {args.drug} 报告 = {countX:,}")

    df = det.detect(terms, N, countX)

    # 控制台输出 Top 信号榜
    cols = ["reaction", "a", "ROR", "ROR_low", "PRR", "PRR_chi2", "IC", "IC025",
            "strength", "n_signals"]
    top = df.head(args.top_signals)
    print(f"\n=== {args.drug} Top 异常不良反应榜（按 IC 降序，前 {args.top_signals}）===")
    with pd.option_context("display.max_rows", None, "display.width", 160):
        print(top[cols].to_string(index=False))

    n_sig = int(df["is_signal"].sum())
    print(f"\n✓ 共判定信号 {n_sig}/{len(df)} 个；强信号 "
          f"{int((df['strength']=='强').sum())} 个、中 "
          f"{int((df['strength']=='中').sum())} 个、弱 "
          f"{int((df['strength']=='弱').sum())} 个。")

    out_path = args.out or f"signals_{args.drug.lower().replace(' ', '_')}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"✓ 完整结果 → {out_path}")


if __name__ == "__main__":
    main()
