# EviFork-Bio — 冲突证据驱动的生物因果假设 Agent

扩展保留竞争有向符号图，复用原 FLASH-P 模拟器，以训练扰动拟合图后验，再选择最能区分机制的干预。当前交付是可运行研究框架与回顾性评估，没有新的生物学发现。上游讨论也将未知新扰动预测留在本轮验证范围之外。[原论文讨论](https://www.biorxiv.org/content/10.64898/2026.06.13.731799v1.full)

## 运行

从仓库根目录执行，Python 3.10+，不新增第三方依赖。代数模拟直接调用原有 `EviFork_Bio_Plant/Claude/Agent/shared/evifork_bio_validator.py`，没有另写生物学传播公式。

```bash
python -m unittest discover -s tests -v
python -m evifork_bio demo --output my_runs/synthetic
python -m evifork_bio prepare Outcome/Arabidopsis/Shoot_Branching_network --output my_runs/shoot.json
python -m evifork_bio run my_runs/shoot.json --output my_runs/shoot_seed17 --seed 17 --budget 3 --original-network Outcome/Arabidopsis/Shoot_Branching_network
```

输出路径应新建。已执行的真实结果见 [结果目录](../research_results/final/README.md)：两个性状、三个划分种子 17/18/19、预算上限 3、每种查询策略五个种子。开发期间的数值稳定修正和默认先验调整及其运行保存在 development_runs；当前结果不是预注册验证研究。

| 输出文件 | 内容 |
|---|---|
| `split_manifest.json` | 四种角色的 ID、论文、独立分量与训练证据哈希 |
| `training_claims.json` / `training_perturbations.json` | 仅训练构建器可见的材料 |
| `conflicts.json` | 竞争状态、来源、先验与截断信息 |
| `hypotheses.json` | 查询前模型状态及后验，不含测试标签 |
| `report.json` | 四种模型的概率评分、覆盖率、校准和预算轨迹 |
| `recommendations_from_query_features.json` | 查询池初始排序，不含真实结果 |

## 方法和假设

同一 source-target-context 的观察符号为候选状态，支持 -1/0/1。默认不增加缺边主张；可选 `--omission-prior 0.1` 引入带显式先验的缺边模型假设。不同 context 必须拆开。

证据可靠度按提取质量分桶，使用 Beta-Binomial 更新。未拟合先验 Beta(3,1) 的均值 0.75 是假设，不是实测可靠度。输入 `audits` 可提供实际独立人工复核记录：`doi`、`quality`、布尔 `correct`、`adjudication: "independent_human"`。同一论文/桶最多计一次；冲突标签要求先审定。审查记录包含留出论文时拒绝运行。程序检查声明，不能证明审查人的独立性。

对每个边对，同一论文的重复提取只贡献一次似然；论文内相反主张作为混合报告。图先验是逐边状态概率之积，依赖“不同论文似然独立”等简化假设。

组合数不超过 `--max-hypotheses` 时枚举全部图；否则使用有保护的 top-k beam，至少保留每个已观察冲突状态的一种实现。保护数量超过容量时拒绝截断。报告保留先验质量；局部保护不保证所有联合拓扑都保留，被截掉的图不会恢复。

图后验满足 `P(H|D_train) ∝ P(H) × ∏ P(y|H,x)^w`。同一论文/干预连通分量内结果的权重合计为 1。方向预测通过预设噪声转换为三分类概率：预测方向 1-noise，其余各 noise/2；默认 noise=0.1 不是测量出的生物学噪声。模型平均为 `Σ_H w_H P(y|H,x)`。

温度缩放仅用校准集，在固定网格上最小化 NLL。不足四条或少于两类就不拟合；同时报告校准前后评分。证据可靠度校准与预测概率校准是不同步骤，没有独立证据标签时前者始终标记 `unfitted_prior_only`。

查询效用为 `I(H;Y|x) = H(Σ_H w_H p_H) - Σ_H w_H H(p_H)`，按效用/成本排序。选定后 Oracle 才揭示结果，每个论文/干预分量最多查询一次。所有候选信息增益为零时提前停止，报告实际花费。比较使用相同预算上限，不隐瞒未使用预算。

## 输入契约和导入

JSON 顶层包含 `format_version: 1`、`metadata`、`claims`、`perturbations`、可选 `audits`。metadata 必须提供 `phenotype_node`、单一 `context`、`source_type`。

claim 包含 `id/source/target/sign/doi/context`，可选 `quality`。DOI 规范化前缀和大小写，仅做语法检查，不宣称已核实原文。只有 `source_type: "synthetic"` 允许 `synthetic:` 来源，不伪造论文 DOI。

perturbation 包含 `id/genes/supply/baseline_genes/baseline_supply/phenotype/context/outcome/dois`，可选正数 cost。四个 modifier/supply 字段都是节点到非负数的字典。outcome 为 -1/0/1。挽救实验必须显式给出突变体比较基线。

导入器只读取原始 `curated_edges.json` 与 `perturbation_dataset.json`，不读精炼拓扑、reconciled 编码或验证结果来构建新假设。只有可唯一匹配的单基因 KO/KD/OE 自动使用 0/0.5/2 作为模拟编码。复杂干预缺少明确 modifier、没有有效 DOI 或无法映射时进入 `import_audit.quarantine`，不猜测。保留原始条件和物种报告；现有数据的粗粒度上下文需要复核。

## 提议与观测闭环

```bash
python -m evifork_bio recommend --state my_runs/synthetic/experiment/hypotheses.json --candidates evifork_bio/examples/candidates.json --output my_runs/proposals.json
python -m evifork_bio observe --state my_runs/synthetic/experiment/hypotheses.json --observation evifork_bio/examples/synthetic_observation.json --output my_runs/updated_state.json
```

候选不需要 outcome 或 DOI。实际观测需要真实 outcome、唯一 experiment_id 和实际 provenance；所附示例明确是合成数据。observe 写入新状态，标记其不再是未触碰的留出评估，不改写原报告。

## 对照与解释边界

| 模型 | 定义 |
|---|---|
| competing_hypotheses | 训练后图后验平均 |
| single_network | 相同训练后验中概率最大的单图 |
| simple_vote | 不同论文计票，平票缺边 |
| original_flashp | 调用实际原方程重放；旧精炼网络标记 reference-only |

公平重建原 FLASH-P 的过程要求见 [Agent 工作流](../research/EVIFORK_BIO_WORKFLOW.md)。未真正运行该基线时输出“未运行”，不杜撰分数。重放旧网络不等于重新运行完整 LLM 管线。

评分为 accuracy、三类 Brier（不除类别数）、NLL、10 箱 top-label ECE、混淆矩阵和后验加权覆盖率。未映射/非收敛模型贡献均匀分布，仍计入总分，避免选择性排除困难样本。

真实数据没有机制真值：熵下降只是代理量。只有合成已知拓扑控制报告真机制后验及达到 0.95 的成本，未达标为 null。少量独立分量上的 ECE 和查询差异不能证明优越性。现有提取物可能已受上游模型选择和 LLM 既有知识影响，因此当前结果是回顾性提取物留出，不是严格盲法原文献提取验证，更不是前瞻性生物发现。
