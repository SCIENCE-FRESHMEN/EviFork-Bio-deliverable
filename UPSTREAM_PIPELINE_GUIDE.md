<p align="center">
  <img src="Images/upstream_causal_network_banner.png" alt="FLASH-P" width="100%" />
</p>

<h1 align="center">上游 FLASH-P 管线指南（Upstream pipeline guide）</h1>

本仓库基于上游 [FLASH-P](https://github.com/CMits/FlashP) 扩展。上游作者身份、源仓库与版权声明见
[NOTICE](NOTICE)，许可条款见 [LICENSE](LICENSE)。

> FLASH-P：把 primary literature 转化为可校验、可扰动测试的因果网络的多阶段系统——
> 文献综述 → 审查 → 构建 → 扰动 → 校验 → 精炼 → 导出。每条边携带 DOI；每个节点接入代数、
> Hill 函数 ODE 与带重启随机游走（RWR）方程，因此网络既可读又可数值模拟。

> **本分发说明（重要）**：上游以「编排提示词 + 交接文件」驱动各阶段。本分发版仅保留功能代码
> （`Agent/shared/`：模拟器、校验器、导出、溯源、可视化）与编排无关的全部研究产物；
> 上游的编排提示词与入口配置不随本仓库分发。`Outcome/` 中的已构建网络与全部校验/导出/溯源
> 工具仍然完整可用；若需恢复编排用法，可参考上游仓库。

---

## 冲突证据假设研究扩展（本仓库新增）

本仓库的核心新增是 `evifork_bio/` 模块：保留竞争有向符号图，用训练扰动拟合图后验，
按预期信息增益/成本选择下一干预。入口见 [evifork_bio/README.md](evifork_bio/README.md)，
一键封装见根目录 `run.py`：

```bash
py -3 run.py test
py -3 run.py demo --output my_runs/synthetic
```

已执行结果与解释边界见 [research_results/final/README.md](research_results/final/README.md)：
当前数据未证明方法稳定优于对照，也没有前瞻性生物发现。

---

## 版本目录

| 目录 | 用途 | 说明 |
|---|---|---|
| `Agent/`（仓库根） | 动物性状（牛）管线 | 原 `EviFork_Bio_Animal/`，作为主版本上移到根目录 |
| [`EviFork_Bio_Plant/`](EviFork_Bio_Plant) | 植物与作物性状 | **从这里开始。**最精炼、测试最充分的版本；研究扩展的模拟器直接调用其 `Agent/shared/evifork_bio_validator.py` |
| [`EviFork_Bio_Medical/`](EviFork_Bio_Medical) | 医学性状 | Alpha：同一管线、医学调校，测试程度不及 Plant |
| [`EviFork_Bio_Paper_Version/`](EviFork_Bio_Paper_Version) | 论文复现 | 论文所用原始管线（完整溯源、多轮审查；三份编排副本哈希相同，已合并为一份） |

---

## 仓库内容

| 路径 | 内容 |
|---|---|
| `evifork_bio/`、`research/`、`research_results/`、`tests/` | 冲突证据假设研究扩展、工作流、结果与测试 |
| `Agent/`、`EviFork_Bio_*/` | 上游管线功能代码（见 [版本目录](#版本目录)） |
| [`Outcome/`](Outcome) | 论文全部输出：13 个网络（6 个拟南芥表型网络、1 个六性状合并网络、6 个其他物种网络——*E. coli*、玉米、杨树、水稻、高粱、小麦）、校验结果、精炼历史、Cytoscape 导出、知识库基线对比（[`Outcome/Upstream_Causal_Network_VS_KG/`](Outcome/Upstream_Causal_Network_VS_KG)）及本地开源模型复现 |
| [`Supplementary Data/`](Supplementary%20Data) | 七份补充 `.xlsx` 表格 |
| [`Images/`](Images) | 横幅与管线示意图 |

`Outcome/` 是上游继承的回顾性校验结果；本地计算评估另见 `research_results/`。两套数据都不构成前瞻性生物发现。

### 在 Cytoscape 中可视化

[`Outcome/Networks/`](Outcome/Networks) 中每个网络都有 `.graphml`，拖入 Cytoscape 并导入
[`Style_Cytoscape.xml`](Outcome/Networks/Style_Cytoscape.xml)（样式 **FLASH-P**）即可按发布配色渲染；
完整步骤见 [`Outcome/Networks/README.md`](Outcome/Networks/README.md)。

---

## 上游归属与许可

上游作者身份、原始仓库与必需的版权声明见 [NOTICE](NOTICE)；项目保留
[CC BY-NC-SA 4.0 许可](LICENSE)。学术使用请引用：

> Mitsanis C, Fortuna NZ, Beveridge C, Kainer D. **Turning decades of biology into accurate
> causal networks with AI agents.** _bioRxiv_ 2026.06.13.731799;
> doi: [10.64898/2026.06.13.731799](https://doi.org/10.64898/2026.06.13.731799)
