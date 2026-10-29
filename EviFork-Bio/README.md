# EviFork-Bio

**证据分歧驱动的生物因果假设研究框架** · Evidence forks for biological causal hypotheses

EviFork-Bio 保留文献中的竞争符号因果图，用扰动数据更新图后验，并按单位成本的预期信息增益选择下一项干预。Evi 代表 evidence，Fork 代表证据分歧产生的竞争机制，Bio 代表生物学应用。

项目基于 [FLASH-P](https://github.com/CMits/FlashP) 扩展，复用其代数模拟器，并包含原有多领域管线与论文配套数据。上游作者、版权和许可证见 [NOTICE](NOTICE) 与 [LICENSE](LICENSE)。建议仓库名为 `EviFork-Bio`，Python 模块名为 `evifork_bio`。

## 快速运行

Python 3.10+，研究扩展不新增第三方依赖。在本目录执行：

```bash
python -B -m unittest discover -s tests -v
python -B -m evifork_bio demo --output my_runs/synthetic
python -B -m evifork_bio --help
```

使用真实网络材料：

```bash
python -B -m evifork_bio prepare Outcome/Arabidopsis/Shoot_Branching_network --output my_runs/shoot.json
python -B -m evifork_bio run my_runs/shoot.json --output my_runs/shoot_seed17 --seed 17 --budget 3 --original-network Outcome/Arabidopsis/Shoot_Branching_network
```

输出目录须使用新路径。完整的数据契约、`recommend` 和 `observe` 命令见 [模块说明](evifork_bio/README.md)，执行约束见 [研究工作流](research/EVIFORK_BIO_WORKFLOW.md)。

## 项目目录

| 路径 | 内容 |
|---|---|
| [evifork_bio/](evifork_bio) | 冲突证据、竞争因果图、后验更新、预测校准与干预选择 |
| [research/](research) | 研究工作流与实验汇总脚本 |
| [research_results/final/](research_results/final) | 两个拟南芥性状的回顾性评估与合成控制 |
| [tests/](tests) | 分组留出、推断、预算及提议/观测闭环测试 |
| [EviFork_Bio_Plant/](EviFork_Bio_Plant) | 基于上游的植物管线，含 Claude、Codex 与 OpenCode 配置 |
| [EviFork_Bio_Medical/](EviFork_Bio_Medical) | 基于上游的医学管线 |
| [EviFork_Bio_Animal/](EviFork_Bio_Animal) | 基于上游的动物管线 |
| [EviFork_Bio_Paper_Version/](EviFork_Bio_Paper_Version) | 基于上游的论文复现管线 |
| [Outcome/](Outcome) | 上游网络、基准与本地模型复现数据 |
| [Supplementary Data/](Supplementary%20Data) | 上游论文补充表格 |
| [UPSTREAM_PIPELINE_GUIDE.md](UPSTREAM_PIPELINE_GUIDE.md) | 原有管线用法，文件路径与命令已适配新名称 |
| [NAMING_MIGRATION.json](NAMING_MIGRATION.json) | 新旧路径、改名前后哈希及命名规则 |
| [DELIVERY_MANIFEST.json](DELIVERY_MANIFEST.json) | 当前交付文件清单与校验值 |

植物管线命令为 `/run-evifork-bio`、`/run-evifork-bio-studio`、`/run-evifork-bio-epistasis`、`/run-evifork-bio-gxe` 和 `/run-evifork-bio-help`；研究扩展命令为 `/run-evifork-bio-hypothesis`。这些命令位于 `EviFork_Bio_Plant/Claude/.claude/commands/`。

## 结果与命名说明

当前交付包含可运行方法和回顾性/合成评估，尚未证明稳定优于对照，也没有前瞻性生物发现。详见 [实际结果](research_results/final/README.md)。

科研 JSON、CSV、图文件和 Office 文件的内容保持原样；历史记录里的 `original_flashp`、`flash_p_version`、上游类名、代码指纹及原路径属于归属或兼容信息。可通过命名对照表解析旧路径。品牌相关文件和目录已改名，`README.md`、`AGENTS.md`、`CLAUDE.md`、`__init__.py` 等约定入口及有明确科学含义的数据名继续保留。
