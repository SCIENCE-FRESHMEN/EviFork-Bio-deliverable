"""Summarize completed runs without changing their predictions or selecting splits."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evifork_bio.data import digest, read_json, write_json


def historical_fingerprints(current_hash):
    """Accept a pre-rename fingerprint only while every renamed implementation file still matches."""
    migration_path = ROOT / "NAMING_MIGRATION.json"
    accepted = {current_hash}
    aliases = {}
    if migration_path.exists():
        migration = read_json(migration_path)
        implementation = [r for r in migration["files"] if r["old_path"].startswith("hypothesis_agent/") and r["old_path"].endswith(".py")]
        expected_paths = {ROOT / r["new_path"] for r in implementation}
        current_paths = set((ROOT / "evifork_bio").glob("*.py"))
        if implementation and expected_paths == current_paths and all(hashlib.sha256((ROOT / r["new_path"]).read_bytes()).hexdigest() == r["after_sha256"] for r in implementation):
            accepted.add(digest({Path(r["old_path"]).name: r["before_sha256"] for r in implementation}))
        aliases = {r["old_path"]: r for r in migration["files"]}
    return accepted, aliases


def summarize(directory):
    directory = Path(directory)
    code_hash = digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted((ROOT / "evifork_bio").glob("*.py"))})
    accepted_hashes, historical_files = historical_fingerprints(code_hash)
    recorded_hashes = set()
    runs = []
    for trait in ("shoot_branching", "flowering_time"):
        for seed in (17, 18, 19):
            path = directory / trait / f"seed{seed}"
            report, split = read_json(path / "report.json"), read_json(path / "split_manifest.json")
            if report["implementation_sha256"] not in accepted_hashes:
                raise ValueError("Run code fingerprint does not match current implementation")
            recorded_hashes.add(report["implementation_sha256"])
            for name, expected in report["upstream_solver_files_sha256"].items():
                old_path = "Flash-P_Plant/Claude/Agent/shared/" + name
                historical = historical_files.get(old_path)
                solver_path = ROOT / (historical["new_path"] if historical else "EviFork_Bio_Plant/Claude/Agent/shared/" + name)
                actual = hashlib.sha256(solver_path.read_bytes()).hexdigest()
                if expected != actual and not (historical and expected == historical["before_sha256"] and actual == historical["after_sha256"]):
                    raise ValueError("Upstream solver fingerprint changed")
            assert report["configuration"]["omission_prior"] == 0.
            assert report["prospective_discovery"] is False
            assert report["evidence_reliability"]["status"] == "unfitted_prior_only"
            runs.append({"trait": trait, "seed": seed, "sizes": report["sizes"],
                         "components": {role: len(row["components"]) for role, row in split["roles"].items()},
                         "conflicts": report["conflicting_pairs"],
                         "hypotheses": report["hypothesis_space"]["retained_hypotheses"],
                         "retained_prior_mass": report["hypothesis_space"]["retained_prior_mass"],
                         "models": {name: {"status": row["status"], "metrics": row["metrics"]}
                                    for name, row in report["baselines"].items()},
                         "query_summary": report["query_summary"]})
    toy = read_json(directory / "synthetic_control/experiment/report.json")
    assert toy["implementation_sha256"] in accepted_hashes
    if recorded_hashes != {toy["implementation_sha256"]}:
        raise ValueError("Cannot combine runs produced by different implementations")
    summary = {"implementation_sha256": toy["implementation_sha256"], "date": "2026-10-29", "runs": runs,
               "synthetic_query_summary": toy["query_summary"],
               "interpretation": "Development-stage retrospective artifact holdouts; no stable superiority or prospective discovery established.",
               "formal_original_flashp_rebuild": "not_run; existing original equations replayed as potentially contaminated references",
               "independent_evidence_audits": "not_available; evidence reliability uses explicitly unfitted prior",
               "test_status": "19 unittest checks passed; upstream light_io emits a pre-existing ResourceWarning for an unclosed read handle"}
    write_json(directory / "summary.json", summary)
    lines = ["# EviFork-Bio — 冲突证据假设 Agent 实际运行结果", "",
        "本页由 `python research/report_results.py research_results/final` 从完整报告生成。所有指定划分都保留，没有按表现筛选。软件已运行，当前数据没有证明方法稳定优于单网络或投票对照，也没有前瞻性生物发现。", "",
        "## 数据和实验设置", "",
        "两个拟南芥性状，种子 17/18/19；预算上限 3；两种查询策略各运行 5 个种子。噪声假设 0.1，不默认添加缺边状态。上游模拟器与实现均保存代码指纹。开发运行及改动原因保存在 `../development_runs/`，当前结果不是预注册研究。", "",
        "| 原始数据 | 原始扰动数 | 可编码扰动数 | 按 DOI 展开的证据条数 | 隔离记录数 |", "|---|---:|---:|---:|---:|"]
    for trait in ("shoot_branching", "flowering_time"):
        data = read_json(directory.parent / "inputs" / f"{trait}.json")
        audit = data["import_audit"]
        lines.append(f"| {trait} | {audit['input_tests']} | {audit['retained_tests']} | {audit['retained_claims']} | {len(audit['quarantine'])} |")
    lines += ["", "分枝原始提取物包含无效 DOI；复杂干预缺少明确数值编码、节点无法唯一匹配等也会隔离。隔离清单和源文件哈希保存在输入 JSON 的 import_audit 中，没有为补齐样本猜测剂量或证据。", "",
        "## 同划分构建对照", "",
        "accuracy 为比例，NLL/Brier/ECE 越低越好。覆盖率为可模拟模型的后验质量；未覆盖模型使用均匀分布并计入总分。只有 4–9 个独立测试分量，不能将样本行数当成独立重复。", "",
        "| 性状/种子 | 测试行/独立分量 | 冲突/图数 | 平均网络 accuracy | 单一 MAP accuracy | 投票 accuracy | 平均网络 NLL | Brier | ECE | 覆盖率 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in runs:
        models = row["models"]
        m = models["competing_hypotheses"]["metrics"]
        lines.append(f"| [{row['trait']}/{row['seed']}]({row['trait']}/seed{row['seed']}/report.json) | {row['sizes']['test']}/{row['components']['test']} | {row['conflicts']}/{row['hypotheses']} | {m['accuracy']:.3f} | {models['single_network']['metrics']['accuracy']:.3f} | {models['simple_vote']['metrics']['accuracy']:.3f} | {m['nll']:.3f} | {m['brier']:.3f} | {m['ece']:.3f} | {m['mean_model_coverage']:.3f} |")
    lines += ["", "开花时间训练材料没有符号冲突，默认只保留一个观察到的图。分枝保留五组候选符号冲突及全部 32 种组合；这些来自粗粒度 context，不代表已证实同条件文献互相矛盾。未映射或未收敛模型贡献无信息分布，低覆盖率限制结果解释，应进一步诊断，不能直接归因于生物机制错误。", "",
        "## 原 FLASH-P 参考重放", "",
        "以下确实调用原方程，但网络原本可能接触过留出结果。它们不是同划分盲法重建的公平对照，不能据此认定哪种方法更优。正式原 FLASH-P 重建和调用过程审查尚未进行。", "",
        "| 性状/种子 | accuracy | NLL | 覆盖率 |", "|---|---:|---:|---:|"]
    for row in runs:
        m = row["models"]["original_flashp"]["metrics"]
        lines.append(f"| {row['trait']}/{row['seed']} | {m['accuracy']:.3f} | {m['nll']:.3f} | {m['mean_model_coverage']:.3f} |")
    lines += ["", "## 相同预算上限的查询重放", "",
        "真实机制标签未知，因此不报告真实数据的机制识别成功率。信息增益为零会停止，不强行用完预算。下表分别报告实际平均成本与查询后的测试 NLL；同一数据上五次查询重放不构成五次独立生物学验证。", "",
        "| 性状/种子 | 信息增益成本 | 随机成本 | 信息增益后 NLL | 随机后 NLL |", "|---|---:|---:|---:|---:|"]
    for row in runs:
        a, b = (row["query_summary"][p] for p in ("information_gain", "random"))
        lines.append(f"| {row['trait']}/{row['seed']} | {a['mean_actual_spend']:.2f} | {b['mean_actual_spend']:.2f} | {a['mean_final_test_nll']:.3f} | {b['mean_final_test_nll']:.3f} |")
    lines += ["", "合成已知拓扑控制用于检查选择算法是否能找到区分机制的干预，不是生物学性能证明。", "",
        "| 合成策略 | 预算上限 | 平均实际成本 | 真机制后验达到 0.95 的比例 | 最终真机制平均后验 |", "|---|---:|---:|---:|---:|"]
    for policy, row in toy["query_summary"].items():
        lines.append(f"| {policy} | {row['budget_ceiling']:.0f} | {row['mean_actual_spend']:.1f} | {row['p95_identification_success_rate']:.2f} | {row['mean_final_true_mechanism_probability']:.3f} |")
    lines += ["", "## 校准与可信度边界", "",
        "预测温度仅在校准集拟合，完整报告保留前后 NLL、Brier、ECE。独立证据审查标签尚不存在，来源可靠度因此是 unfitted_prior_only；不能称为已获得实证校准的证据可信度。", "",
        "文件级分组隔离已实现并测试，但旧提取物可能包含上游模型选择或 LLM 已有知识。正式验证需要冻结语料、按划分盲法提取与构建、独立证据复核，以及有足够分量的测试集。未知真实新扰动仍需实际实验。", "",
        "19 项测试已通过，包括结果标签不参与选点、修改测试标签不改变拟合、论文和干预联合隔离、少数冲突保留、查询预算、非收敛降级、实际方程与基线声明一致性、提议/观测闭环。原 light_io 加载器会发出已有文件读取句柄 ResourceWarning；本轮未改动上游实现。", "",
        "[实现说明](../../evifork_bio/README.md) · [Agent 工作流](../../research/EVIFORK_BIO_WORKFLOW.md) · [机器可读汇总](summary.json)", ""]
    (directory / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Summarized {len(runs)} biological artifact holdout runs and one synthetic control.")


if __name__ == "__main__":
    summarize(sys.argv[1] if len(sys.argv) > 1 else ROOT / "research_results/final")
