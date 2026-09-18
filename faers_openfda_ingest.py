#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAERS 取数脚本草稿（基于 openFDA 免费 API）
=================================================
用途：从 FDA 公开「药品不良事件」库拉取数据，扁平化为一行=一份报告，
      保存为 CSV，供后续【信号检测】与【严重性评价预测】建模使用。

接口说明：
  - 端点: https://api.fda.gov/drug/event.json
  - 免费、免 key（但匿名限速约 40 req/min、单次最多返回 100 条）。
  - 申请 key(免费)后把 api_key 填上，限速放宽到约 240 req/min。

环境：
  pip install requests pandas
  或本机用: python faers_openfda_ingest.py --drug ASPIRIN --max 5000

注意：
  - openFDA 是 FAERS 的「清洗后」版本，字段名与原始 FAERS ASCII 略有差异，
    但足够做入门级信号检测与原型建模。
  - 数据归属公开，纯做个人学习/作品集，合乎合规要求。
"""

import argparse
import time
import sys
import json

import requests
import pandas as pd

API_BASE = "https://api.fda.gov/drug/event.json"
PAGE_SIZE = 100          # openFDA 单次上限
REQUEST_DELAY = 0.3      # 每次请求间隔(秒)，避免触发限速；有 key 可降到 0.05
API_KEY = ""             # 可选：填上你的免费 key 提升限速


def build_query(drug: str, date_from: str | None = None) -> str:
    """构造 openFDA 查询语句（Lucene 语法）。

    注意(openFDA 实测坑)：
      - 可搜索字段是 `patient.drug.medicinalproduct`，不是 `drugname`。
      - 药名**不要加引号**——带引号会返回 404(无匹配)。
      - 药名用大写，做 term 匹配（如 ASPIRIN 会命中含该 token 的记录）。
    """
    q = f'patient.drug.medicinalproduct:{drug.upper()}'
    if date_from:
        # 限定接收日期，避免一次性拉全量历史（数据量极大）
        q += f' AND receivedate:[{date_from} TO 2026-12-31]'
    return q


def fetch_page(search_after: int, query: str) -> dict:
    """拉取单页（skip 分页）。返回解析后的 JSON 或抛错。"""
    params = {
        "search": query,
        "limit": PAGE_SIZE,
        "skip": search_after,
    }
    if API_KEY:
        params["api_key"] = API_KEY

    resp = requests.get(API_BASE, params=params, timeout=30)
    if resp.status_code == 429:
        # 触发限速：退避后由调用方重试
        raise RuntimeError("RATE_LIMIT")
    resp.raise_for_status()
    return resp.json()


def flatten_result(res: dict) -> dict:
    """把一份报告里「标题级 + 患者级」的字段压平（药品/反应用列表拼接）。"""
    patient = res.get("patient", {})

    # 患者用药（取第一条用药基本信息，其余药名汇总）
    drugs = patient.get("drug", [])
    primary_drug = drugs[0] if drugs else {}
    all_drug_names = "; ".join(
        d.get("medicinalproduct", "") for d in drugs if d.get("medicinalproduct")
    )

    # 不良反应（MedDRA 首选术语）
    reactions = patient.get("reaction", [])
    reaction_terms = "; ".join(
        r.get("reactionmeddrapt", "") for r in reactions if r.get("reactionmeddrapt")
    )

    # 严重性字段（openFDA: serious="1"=严重, "2"=非严重；
    #   seriousnessdeath 等仅在为真时存在，缺失即代表否）
    is_serious = int(str(res.get("serious", "")) == "1")
    sev_death = int(str(res.get("seriousnessdeath", "")) == "1")
    sev_hosp = int(str(res.get("seriousnesshospitalization", "")) == "1")
    sev_life = int(str(res.get("seriousnesslifethreatening", "")) == "1")
    sev_disab = int(str(res.get("seriousnessdisabling", "")) == "1")
    sev_cong = int(str(res.get("seriousnesscongenitalanomali", "")) == "1")
    sev_inter = int(str(res.get("seriousnessintervention", "")) == "1")

    return {
        "safetyreportid": res.get("safetyreportid", ""),
        "receivedate": res.get("receivedate", ""),
        # 本项目「严重性评价预测」的目标变量 Y
        "is_serious": is_serious,
        "serious_death": sev_death,
        "serious_hospitalization": sev_hosp,
        "serious_lifethreatening": sev_life,
        "serious_disabling": sev_disab,
        # 患者特征（建模 X）
        "patient_sex": patient.get("patientsex", ""),
        "patient_age": patient.get("patientonsetage", ""),
        "age_unit": patient.get("patientonsetageunit", ""),
        "patient_weight": patient.get("patientweight", ""),   # 多数报告缺失
        "num_drugs": len(drugs),                              # 合并用药数(重要特征)
        "primary_drugname": primary_drug.get("medicinalproduct", ""),
        "primary_route": primary_drug.get("drugadministrationroute", ""),  # 编码值
        "primary_indication": primary_drug.get("drugindication", ""),
        "all_drug_names": all_drug_names,
        "reactions": reaction_terms,
        "reporttype": res.get("reporttype", ""),             # 1=初始 2=随访 3=Direct
        "primarysource_country": res.get("primarysource", {}).get("country", ""),
    }


def collect(drug: str, max_records: int, date_from: str | None) -> pd.DataFrame:
    """分页拉取并扁平化，返回 DataFrame。"""
    query = build_query(drug, date_from)
    rows = []
    skip = 0

    while len(rows) < max_records:
        try:
            data = fetch_page(skip, query)
        except RuntimeError:  # 限速
            print("  ⚠ 触发限速，退避 5 秒后重试…")
            time.sleep(5)
            continue

        results = data.get("results", [])
        if not results:
            print(f"  已无更多数据，skip={skip}")
            break

        for r in results:
            rows.append(flatten_result(r))
            if len(rows) >= max_records:
                break

        skip += PAGE_SIZE
        print(f"  已抓取 {len(rows)} 条…")
        time.sleep(REQUEST_DELAY)

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="openFDA FAERS 取数草稿")
    parser.add_argument("--drug", default="ASPIRIN", help="药品通用名，如 ASPIRIN / METFORMIN")
    parser.add_argument("--max", type=int, default=2000, help="最多抓取报告数")
    parser.add_argument("--date_from", default=None, help="接收日期下限，如 2023-01-01")
    parser.add_argument("--out", default=None, help="输出 CSV 路径")
    args = parser.parse_args()

    out_path = args.out or f"faers_{args.drug.lower().replace(' ', '_')}.csv"

    print(f"▶ 拉取药物: {args.drug}  目标条数: {args.max}")
    df = collect(args.drug, args.max, args.date_from)

    if df.empty:
        print("✗ 未取到任何数据，请检查药品名拼写或放宽 date_from。")
        sys.exit(1)

    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"✓ 完成：{len(df)} 条 → {out_path}")
    print(f"  其中严重报告 {int(df['is_serious'].sum())} 条 "
          f"({df['is_serious'].mean()*100:.1f}%)")
    print("  字段预览：", list(df.columns)[:8], "…")


if __name__ == "__main__":
    main()
