#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAERS 本地信号检测（基于官方 ASCII 季度原始数据，完全离线）
=========================================================
用途：直接读取本地 FAERS 季度 zip（DEMO/DRUG/REAC 三张表），
      对指定药品做不成比例分析（ROR / PRR / BCPNN-IC），输出 Top 信号榜。

相比 openFDA API 版的优势：
  - 完全离线，不受公司网络/流量限制
  - 数据更全（API 有字段与速率限制，本地是完整原始报告）
  - 可自由选择季度范围

数据格式（FDA 官方 ASCII）：
  - 分隔符 `$`，编码 latin-1
  - DEMO: primaryid, caseid, caseversion, i_f_code, event_dt, ...
  - DRUG: primaryid, caseid, drug_seq, role_cod, drugname, prod_ai, ...
          role_cod: PS=首要怀疑 SS=次要怀疑 C=并用 I=相互作用
  - REAC: primaryid, caseid, pt(不良反应首选术语), drug_rec_act

运行示例：
  python faers_local_signals.py --drug ASPIRIN
  python faers_local_signals.py --drug METFORMIN --year-from 2022 --year-to 2025 --top 25
  python faers_local_signals.py --drug IBUPROFEN --role PS --out signals_ibuprofen.csv
"""

import argparse
import os
import re
import sys
import zipfile
from collections import Counter

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import faers_signal_detection as fsd  # noqa: E402

# 本地 FAERS 季度数据目录（可 --data-dir 覆盖）
DEFAULT_DATA_DIR = r"F:\郑州大学\fares数据-2018-2025"

# 同时支持新命名 faers_ascii_2018Q1.zip 与旧命名 aers_ascii_2004q1.zip
# （FDA 的 AERS 于 2012 年更名为 FAERS，更早的数据文件前缀是 aers_）
ZIP_RE = re.compile(r"(?:faers|aers)_ascii_(\d{4})[qQ](\d)\.zip$", re.I)

# 全盘扫描时跳过的系统/噪声目录
SKIP_DIRS = {
    "$RECYCLE.BIN", "System Volume Information", "Windows",
    "Program Files", "Program Files (x86)", "AppData", "ProgramData",
    "node_modules", ".git", "__pycache__", ".venv", "venv",
}


def scan_candidate_dirs(drives=None, max_depth=3):
    """扫描各盘符，找出含有 FAERS/AERS 季度 zip 的目录。

    返回 [(dir_path, n_quarters, first_label, last_label), ...]，按季度数降序。
    """
    if drives is None:
        drives = [f"{c}:/" for c in "CDEFGHIJ"]
    pat = re.compile(r"(?:faers|aers)_ascii_(\d{4})[qQ](\d)\.zip$", re.I)
    result = []
    for drv in drives:
        if not os.path.exists(drv):
            continue
        for root, dirs, files in os.walk(drv):
            depth = root[len(drv):].count(os.sep)
            if depth >= max_depth:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs
                       if d not in SKIP_DIRS and not d.startswith(".")]
            hits = []
            for f in files:
                m = pat.match(f)
                if m:
                    hits.append((int(m.group(1)), int(m.group(2))))
            if hits:
                hits.sort()
                result.append((
                    root, len(hits),
                    f"{hits[0][0]}Q{hits[0][1]}",
                    f"{hits[-1][0]}Q{hits[-1][1]}",
                ))
    result.sort(key=lambda x: -x[1])
    return result


def discover_quarters(data_dir, year_from=None, year_to=None):
    """扫描目录，返回 [(quarter_label, zip_path), ...]，按时间升序。"""
    found = []
    for name in os.listdir(data_dir):
        m = ZIP_RE.match(name)
        if not m:
            continue
        year, q = int(m.group(1)), int(m.group(2))
        if year_from and year < year_from:
            continue
        if year_to and year > year_to:
            continue
        found.append((f"{year}Q{q}", os.path.join(data_dir, name)))
    found.sort(key=lambda x: (int(x[0][:4]), int(x[0][-1])))
    return found


def _pick_member(z, kind):
    """在 zip 中定位 ASCII/<KIND>YYQn.txt（忽略大小写）。"""
    pat = re.compile(rf"ASCII/{kind}\d\d[Qq]\d\.txt$", re.I)
    for n in z.namelist():
        if pat.search(n):
            return n
    return None


def build_counts(quarters, drug_upper, roles=None, fuzzy=False,
                 verbose=True, on_quarter=None):
    """流式扫描季度 zip，构建不成比例分析所需的全部计数。

    返回 (S_X, a_counter, tot_counter, N)
      S_X  : 含目标药的 primaryid 集合
      a[]  : 目标药人群中，各不良反应(pt)的报告数
      tot[]: 全库中，各不良反应(pt)的报告数
      N    : 时间窗内报告总数
    """
    S_X = set()
    a = Counter()
    tot = Counter()
    N = 0

    total_q = len(quarters)
    for qi, (label, zp) in enumerate(quarters):
        if on_quarter:
            on_quarter(label, qi, total_q)
        if verbose:
            print(f"  [{label}] 读取中…", flush=True)
        try:
            with zipfile.ZipFile(zp) as z:
                demo_n = _pick_member(z, "DEMO")
                drug_n = _pick_member(z, "DRUG")
                reac_n = _pick_member(z, "REAC")
                if not (demo_n and drug_n and reac_n):
                    print(f"  [{label}] 缺少 DEMO/DRUG/REAC，跳过", flush=True)
                    continue

                # --- DEMO: 统计报告总数 ---
                with z.open(demo_n) as f:
                    n_rows = sum(1 for _ in f) - 1
                N += max(n_rows, 0)
                if verbose:
                    print(f"  [{label}] 报告数 {n_rows:,}", flush=True)

                # --- DRUG: 找出含目标药的报告 ---
                hit = 0
                # 注意：按字节比较，避免 bytes/str 类型不匹配导致永远命中不了
                drug_b = drug_upper.encode("latin-1")
                roles_b = ({r.encode("latin-1") for r in roles}
                           if roles else None)
                with z.open(drug_n) as f:
                    # 按表头名定位列，兼容旧 AERS（无 prod_ai）与新 FAERS
                    hdr = f.readline().decode("latin-1").rstrip("\r\n").split("$")
                    hm = {h.strip().lower(): i for i, h in enumerate(hdr)}
                    i_pid = hm.get("primaryid", 0)
                    i_role = hm.get("role_cod")
                    i_name = hm.get("drugname")
                    i_ai = hm.get("prod_ai")  # 早期 AERS 无此列 → None
                    for raw in f:
                        parts = raw.split(b"$")
                        if len(parts) <= i_pid:
                            continue
                        if roles_b and i_role is not None:
                            if len(parts) <= i_role or parts[i_role] not in roles_b:
                                continue
                        name = parts[i_name].upper() if (i_name is not None
                                                         and len(parts) > i_name) else b""
                        ai = parts[i_ai].upper() if (i_ai is not None
                                                     and len(parts) > i_ai) else b""
                        if (name == drug_b or ai == drug_b
                                or (fuzzy and (drug_b in name or drug_b in ai))):
                            S_X.add(parts[i_pid])
                            hit += 1
                if verbose:
                    print(f"  [{label}] 命中目标药 {hit:,} 条用药记录", flush=True)

                # --- REAC: 统计各不良反应 ---
                with z.open(reac_n) as f:
                    hdr = f.readline().decode("latin-1").rstrip("\r\n").split("$")
                    hm = {h.strip().lower(): i for i, h in enumerate(hdr)}
                    i_pid = hm.get("primaryid", 0)
                    i_pt = hm.get("pt", 2)
                    for raw in f:
                        parts = raw.split(b"$")
                        if len(parts) <= max(i_pid, i_pt):
                            continue
                        pid = parts[i_pid]
                        pt = parts[i_pt].decode("latin-1").strip()
                        if not pt:
                            continue
                        if pid in S_X:
                            a[pt] += 1
                        tot[pt] += 1
        except Exception as e:
            print(f"  [{label}] 读取失败: {type(e).__name__}: {e}", flush=True)
            continue

    return S_X, a, tot, N


def detect(drug, quarters, roles=None, fuzzy=False, top=None, verbose=True,
           on_quarter=None):
    """执行本地信号检测，返回 (DataFrame, N, countX)。"""
    drug_upper = drug.strip().upper()
    S_X, a, tot, N = build_counts(quarters, drug_upper, roles, fuzzy, verbose,
                                  on_quarter)
    countX = len(S_X)

    if verbose:
        print(f"\n汇总：报告总数 N={N:,}，含目标药 countX={countX:,}，"
              f"唯一不良反应词 {len(tot):,}", flush=True)

    rows = []
    # 只评估在目标药人群中至少出现过的反应（a>=1）
    candidates = a.most_common() if top is None else a.most_common(top * 3)
    for pt, a_val in candidates:
        c_val = max(tot[pt] - a_val, 0)
        b_val = max(countX - a_val, 0)
        d_val = max(N - a_val - b_val - c_val, 0)

        m = fsd.disproportionality(a_val, b_val, c_val, d_val)
        f = fsd.signal_flags(a_val, m)
        row = {"reaction": pt, "a": a_val, "b": b_val, "c": c_val, "d": d_val}
        row.update(m)
        row.update(f)
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df, N, countX

    df = df.sort_values(by=["IC", "ROR"], ascending=[False, False],
                        na_position="last").reset_index(drop=True)
    if top:
        df = df.head(top).reset_index(drop=True)
    return df, N, countX


SERIOUS_CODES = {"DE", "LT", "HO", "DS", "CA", "RI"}  # 死亡/危及生命/住院/残疾/先天异常/其他严重


def extract_cases(quarters, drug_upper, roles=None, fuzzy=False,
                  verbose=True, on_quarter=None, with_outcomes=True):
    """提取「含目标药」的全部报告（病例级明细），用于导出原始数据集。

    与 detect() 的区别：detect 只输出聚合后的信号榜；
    extract_cases 保留每一份报告的字段，便于二次分析。

    返回 (DataFrame, N, countX)
      N      = 时间窗内报告总数
      countX = 含目标药的报告数（即导出行数）
    列：primaryid / caseid / event_dt / age / age_cod / sex / wt /
        reporter_country / occr_country / drug_name / drug_role /
        drug_ai / drug_route / reactions / n_reactions /
        outcome_codes / serious
    """
    S_X = set()
    drugs = {}   # pid -> [(name, role, ai, route), ...]
    demo = {}    # pid -> (caseid, event_dt, age, age_cod, sex, wt, rc, occ)
    reacs = {}   # pid -> [pt, ...]
    outcs = {}   # pid -> [outc_cod, ...]
    N = 0

    drug_b = drug_upper.encode("latin-1")
    roles_b = ({r.encode("latin-1") for r in roles} if roles else None)
    total_q = len(quarters)

    for qi, (label, zp) in enumerate(quarters):
        if on_quarter:
            on_quarter(label, qi, total_q)
        if verbose:
            print(f"  [{label}] 提取中…", flush=True)
        try:
            with zipfile.ZipFile(zp) as z:
                drug_n = _pick_member(z, "DRUG")
                demo_n = _pick_member(z, "DEMO")
                reac_n = _pick_member(z, "REAC")
                outc_n = _pick_member(z, "OUTC") if with_outcomes else None

                # ---- 1) DRUG：锁定含目标药的报告 ----
                with z.open(drug_n) as f:
                    hdr = f.readline().decode("latin-1").rstrip("\r\n").split("$")
                    hm = {h.strip().lower(): i for i, h in enumerate(hdr)}
                    i_pid = hm.get("primaryid", 0)
                    i_role = hm.get("role_cod")
                    i_name = hm.get("drugname")
                    i_ai = hm.get("prod_ai")
                    i_route = hm.get("route")

                    def gv(parts, idx):
                        if idx is None or len(parts) <= idx:
                            return ""
                        return parts[idx].decode("latin-1").strip()

                    for raw in f:
                        parts = raw.split(b"$")
                        if len(parts) <= i_pid:
                            continue
                        if roles_b and i_role is not None:
                            if len(parts) <= i_role or parts[i_role] not in roles_b:
                                continue
                        nm = (parts[i_name].upper() if (i_name is not None
                                                        and len(parts) > i_name) else b"")
                        ai = (parts[i_ai].upper() if (i_ai is not None
                                                      and len(parts) > i_ai) else b"")
                        if not (nm == drug_b or ai == drug_b
                                or (fuzzy and (drug_b in nm or drug_b in ai))):
                            continue
                        pid = parts[i_pid]
                        S_X.add(pid)
                        drugs.setdefault(pid, []).append((
                            nm.decode("latin-1"),
                            gv(parts, i_role),
                            ai.decode("latin-1"),
                            gv(parts, i_route),
                        ))

                # ---- 2) DEMO：全量计数 + 目标药报告的人口学 ----
                with z.open(demo_n) as f:
                    hdr = f.readline().decode("latin-1").rstrip("\r\n").split("$")
                    hm = {h.strip().lower(): i for i, h in enumerate(hdr)}
                    i_pid = hm.get("primaryid", 0)
                    i_case = hm.get("caseid")
                    i_evt = hm.get("event_dt")
                    i_age = hm.get("age")
                    i_agec = hm.get("age_cod")
                    i_sex = hm.get("sex")
                    i_wt = hm.get("wt")
                    i_rc = hm.get("reporter_country")
                    i_occ = hm.get("occr_country")

                    def gg(parts, idx):
                        if idx is None or len(parts) <= idx:
                            return ""
                        return parts[idx].decode("latin-1").strip()

                    n = 0
                    for raw in f:
                        n += 1
                        parts = raw.split(b"$")
                        if len(parts) <= i_pid:
                            continue
                        pid = parts[i_pid]
                        if pid not in S_X:
                            continue
                        demo[pid] = (gg(parts, i_case), gg(parts, i_evt),
                                     gg(parts, i_age), gg(parts, i_agec),
                                     gg(parts, i_sex), gg(parts, i_wt),
                                     gg(parts, i_rc), gg(parts, i_occ))
                    N += max(n - 1, 0)

                # ---- 3) REAC：目标药报告的不良反应 ----
                with z.open(reac_n) as f:
                    hdr = f.readline().decode("latin-1").rstrip("\r\n").split("$")
                    hm = {h.strip().lower(): i for i, h in enumerate(hdr)}
                    i_pid = hm.get("primaryid", 0)
                    i_pt = hm.get("pt", 2)
                    for raw in f:
                        parts = raw.split(b"$")
                        if len(parts) <= max(i_pid, i_pt):
                            continue
                        pid = parts[i_pid]
                        if pid not in S_X:
                            continue
                        pt = parts[i_pt].decode("latin-1").strip()
                        if pt:
                            reacs.setdefault(pid, []).append(pt)

                # ---- 4) OUTC：结局 ----
                if outc_n:
                    with z.open(outc_n) as f:
                        hdr = f.readline().decode("latin-1").rstrip("\r\n").split("$")
                        hm = {h.strip().lower(): i for i, h in enumerate(hdr)}
                        i_pid = hm.get("primaryid", 0)
                        i_code = hm.get("outc_cod", 1)
                        for raw in f:
                            parts = raw.split(b"$")
                            if len(parts) <= max(i_pid, i_code):
                                continue
                            pid = parts[i_pid]
                            if pid not in S_X:
                                continue
                            code = parts[i_code].decode("latin-1").strip()
                            if code:
                                outcs.setdefault(pid, []).append(code)
        except Exception as e:
            if verbose:
                print(f"  [{label}] 提取失败: {type(e).__name__}: {e}", flush=True)
            continue

    # ---------------- 组装 ----------------
    rows = []
    for pid in S_X:
        d = demo.get(pid, ("", "", "", "", "", "", "", ""))
        dl = drugs.get(pid, [])
        rl = reacs.get(pid, [])
        ol = outcs.get(pid, [])
        rows.append({
            "primaryid": pid.decode("latin-1"),
            "caseid": d[0],
            "event_dt": d[1],
            "age": d[2],
            "age_cod": d[3],
            "sex": d[4],
            "wt": d[5],
            "reporter_country": d[6],
            "occr_country": d[7],
            "drug_name": "; ".join(sorted({x[0] for x in dl})),
            "drug_role": "; ".join(sorted({x[1] for x in dl if x[1]})),
            "drug_ai": "; ".join(sorted({x[2] for x in dl if x[2]})),
            "drug_route": "; ".join(sorted({x[3] for x in dl if x[3]})),
            "reactions": " | ".join(rl),
            "n_reactions": len(rl),
            "outcome_codes": " | ".join(ol),
            "serious": "Y" if any(c in SERIOUS_CODES for c in ol) else "N",
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("event_dt").reset_index(drop=True)
    return df, N, len(S_X)


def main():
    ap = argparse.ArgumentParser(
        description="FAERS 本地信号检测（离线，基于官方 ASCII 季度数据）")
    ap.add_argument("--drug", required=True, help="药品通用名（英文，如 ASPIRIN）")
    ap.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="季度 zip 所在目录")
    ap.add_argument("--year-from", type=int, default=None, help="起始年份")
    ap.add_argument("--year-to", type=int, default=None, help="截止年份")
    ap.add_argument("--role", default="ALL",
                    help="用药角色过滤：ALL(默认) / PS / SS / C / I，可逗号组合")
    ap.add_argument("--fuzzy", action="store_true",
                    help="药品名模糊匹配（子串），可覆盖 ASPIRIN 81MG 等变体")
    ap.add_argument("--top", type=int, default=25, help="输出 Top N 信号")
    ap.add_argument("--out", default=None, help="信号结果 CSV 路径")
    ap.add_argument("--extract", default=None,
                    help="导出含该药的【原始病例数据】到指定 CSV（病例级明细）")
    args = ap.parse_args()

    if not os.path.isdir(args.data_dir):
        print(f"错误：数据目录不存在 -> {args.data_dir}")
        print("请用 --data-dir 指定正确路径。")
        sys.exit(1)

    quarters = discover_quarters(args.data_dir, args.year_from, args.year_to)
    if not quarters:
        print(f"错误：在 {args.data_dir} 未找到任何 faers_ascii_*.zip")
        sys.exit(1)

    roles = None
    if args.role.upper() != "ALL":
        roles = {r.strip().upper() for r in args.role.split(",")}

    print(f"数据目录：{args.data_dir}")
    print(f"季度范围：{quarters[0][0]} ~ {quarters[-1][0]}（共 {len(quarters)} 个季度）")
    print(f"目标药品：{args.drug.upper()}    角色过滤：{args.role}")
    print("-" * 60)

    # ---------- 导出原始病例数据 ----------
    if args.extract:
        print("模式：导出原始病例数据（病例级明细）")
        cdf, cN, cX = extract_cases(quarters, args.drug.upper(), roles,
                                    args.fuzzy)
        if cdf.empty:
            print("\n未匹配到该药品的病例，请检查药名或加 --fuzzy。")
            sys.exit(0)
        cdf.to_csv(args.extract, index=False, encoding="utf-8-sig")
        print(f"\n导出完成：{len(cdf):,} 条病例"
              f"（时间窗内共 {cN:,} 份报告，含该药 {cX:,} 份）")
        print(f"文件：{args.extract}")
        print(f"字段：{', '.join(cdf.columns)}")
        if not args.out:
            sys.exit(0)

    df, N, countX = detect(args.drug, quarters, roles, args.fuzzy, args.top)

    if df.empty:
        print("\n未找到任何不良反应记录，请检查药名或改用 --fuzzy。")
        sys.exit(0)

    show = ["reaction", "a", "ROR", "ROR_low", "PRR", "PRR_chi2",
            "IC", "IC025", "strength", "n_signals"]
    print("\n" + "=" * 70)
    print(f"{args.drug.upper()} · Top 信号（本地 FAERS 数据）")
    print("=" * 70)
    print(df[show].to_string(index=False))

    if args.out:
        df.to_csv(args.out, index=False, encoding="utf-8-sig")
        print(f"\n已保存：{args.out}")


if __name__ == "__main__":
    main()
