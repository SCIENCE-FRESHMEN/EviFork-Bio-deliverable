# EviFork-Bio

**证据分歧驱动的生物因果假设研究框架** · Evidence forks for biological causal hypotheses

EviFork-Bio 保留文献中的竞争符号因果图（competing signed causal graphs），用扰动数据更新图后验，
并按单位成本的预期信息增益选择下一项干预。Evi 代表 evidence，Fork 代表证据分歧产生的竞争机制，
Bio 代表生物学应用。项目基于上游 [FLASH-P](https://github.com/CMits/FlashP)（文献 → 可校验因果网络
的多阶段管线）扩展，复用其代数模拟器；上游归属与许可见 [NOTICE](NOTICE) 与 [LICENSE](LICENSE)。

当前交付包含可运行的研究方法、回顾性/合成评估，以及上游论文的网络与补充数据。**当前数据尚未证明
新方法稳定优于对照，也没有前瞻性生物发现**——详见 [实际结果](research_results/final/README.md)。

## 功能模块

| 模块 | 内容 |
|---|---|
| [evifork_bio/](evifork_bio) | 研究扩展核心：冲突证据保留、竞争因果图枚举（beam 保护）、Beta-Binomial 证据可靠度更新、温度缩放校准、信息增益干预选择、提议/观测闭环 |
| [research/](research) | 研究工作流规范（[EVIFORK_BIO_WORKFLOW.md](research/EVIFORK_BIO_WORKFLOW.md)）与结果汇总脚本（[report_results.py](research/report_results.py)，带实现指纹核验） |
| [research_results/](research_results) | 真实运行结果：`final/`（两个拟南芥性状 × 种子 17/18/19 + 合成对照）、`inputs/`（原始提取）、`development_runs/`（开发期运行） |
| [tests/](tests) | 19 项测试：分组留出防泄漏、推断、预算、提议/观测闭环等 |
| [Agent/](Agent) | 上游动物（牛）管线功能代码（主版本；原 `EviFork_Bio_Animal/`） |
| [EviFork_Bio_Plant/](EviFork_Bio_Plant) | 植物性状管线（最完整；研究扩展的模拟器直接调用其 `Agent/shared/evifork_bio_validator.py`） |
| [EviFork_Bio_Medical/](EviFork_Bio_Medical) | 医学性状管线（Alpha） |
| [EviFork_Bio_Paper_Version/](EviFork_Bio_Paper_Version) | 论文复现管线（完整溯源版） |
| [Outcome/](Outcome) | 上游论文输出：6 个拟南芥表型网络、1 个六性状合并网络、6 个其他物种网络、知识库基线对比与本地模型复现 |
| [Supplementary Data/](Supplementary%20Data) | 上游论文七份补充表格（.xlsx） |
| [UPSTREAM_PIPELINE_GUIDE.md](UPSTREAM_PIPELINE_GUIDE.md) | 上游管线说明与归属 |

## 一键入口

Python 3.10+，研究扩展不新增第三方依赖。在仓库根目录：

```bash
py -3 run.py test                                   # 运行全部 19 项测试
py -3 run.py demo --output my_runs/demo             # 合成已知拓扑对照（非生物学结果）
py -3 run.py report                                 # 重新生成 research_results/final 汇总
```

使用真实网络材料做回顾性留出评估：

```bash
py -3 run.py prepare Outcome/Arabidopsis/Shoot_Branching_network --output my_runs/shoot.json
py -3 run.py run my_runs/shoot.json --output my_runs/shoot_seed17 --seed 17 --budget 3 --original-network Outcome/Arabidopsis/Shoot_Branching_network
```

闭环用法（输出路径必须是新路径）：

```bash
py -3 run.py recommend --state my_runs/synthetic/experiment/hypotheses.json --candidates evifork_bio/examples/candidates.json --output my_runs/proposals.json
py -3 run.py observe --state my_runs/synthetic/experiment/hypotheses.json --observation evifork_bio/examples/synthetic_observation.json --output my_runs/updated_state.json
```

各子命令的参数与 `python -m evifork_bio --help` 一致；数据契约见
[evifork_bio/README.md](evifork_bio/README.md)。

## 实际结果（摘要）

数据与完整表格见 [research_results/final/README.md](research_results/final/README.md)（由
`run.py report` 从完整报告生成，未按表现筛选划分）。

**输入与隔离**（出处：`research_results/final/README.md`，来自输入 JSON 的 `import_audit`）：

| 性状 | 原始扰动数 | 可编码扰动数 | 按 DOI 展开的证据条数 | 隔离记录数 |
|---|---:|---:|---:|---:|
| shoot_branching | 201 | 47 | 358 | 184 |
| flowering_time | 194 | 156 | 380 | 38 |

**同划分构建对照 accuracy**（种子 17/18/19；competing_hypotheses 模型；出处：`research_results/final/summary.json`）：

| 性状 | seed 17 | seed 18 | seed 19 |
|---|---:|---:|---:|
| shoot_branching | 0.333 | 0.111 | 0.556 |
| flowering_time | 0.595 | 0.487 | 0.000 |

**合成已知拓扑对照**（预算上限 3，5 次查询重放；出处：`research_results/final/summary.json` 的
`synthetic_query_summary`）：信息增益策略真机制后验达到 0.95 的比例 **1.00**，平均实际成本 **1.0**，
最终真机制平均后验 **0.974**；随机策略对应 **0.00 / 3.0 / 0.500**。

**测试**：19 项测试全部通过（`run.py test`；上游 `light_io` 存在一个原有的 ResourceWarning）。

解释边界：真实数据没有机制真值；开花时间训练材料无符号冲突；只有 4–9 个独立测试分量；
证据可靠度目前是 `unfitted_prior_only`。详见
[结果页的校准与可信度边界](research_results/final/README.md)。

## 仓库结构

```text
EviFork-Bio-deliverable/
├── run.py                    # 一键入口（test / demo / prepare / run / recommend / observe / report）
├── evifork_bio/              # 研究扩展核心模块
├── research/                 # 工作流规范 + 结果汇总脚本
├── research_results/         # final / inputs / development_runs
├── tests/                    # 19 项单元测试
├── Agent/                    # 上游动物（牛）管线代码（主版本）
├── EviFork_Bio_Plant/        # 植物管线（研究扩展调用的模拟器所在）
├── EviFork_Bio_Medical/      # 医学管线（Alpha）
├── EviFork_Bio_Paper_Version/# 论文复现管线
├── Outcome/                  # 上游论文网络、校验、补充数据
├── Supplementary Data/       # 七份补充表格
├── Images/                   # 横幅与管线示意图
├── UPSTREAM_PIPELINE_GUIDE.md
├── LICENSE / NOTICE
```

## 依赖

- Python 3.10+（标准库即可运行研究扩展与全部测试）
- 上游管线的可选功能（文献溯源检索、可视化渲染）需要各自依赖，见对应目录内说明
  （如 [Agent/shared/provenance/](Agent/shared/provenance)、[EviFork_Bio_Plant/Agent/shared/visual/](EviFork_Bio_Plant/Agent/shared/visual)）

## 引用与许可

上游学术引用与归属见 [UPSTREAM_PIPELINE_GUIDE.md](UPSTREAM_PIPELINE_GUIDE.md) 与
[NOTICE](NOTICE)；项目保留 [CC BY-NC-SA 4.0 许可](LICENSE)。
研究扩展的论文讨论见 [bioRxiv 2026.06.13.731799](https://www.biorxiv.org/content/10.64898/2026.06.13.731799v1.full)。
