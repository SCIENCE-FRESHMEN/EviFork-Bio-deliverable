# EviFork_Bio_Plant — 植物性状管线（主版本）

FLASH-P 的轻量化植物管线，目标是在单次会话内产出一份完整校验过的因果网络。科学逻辑与完整管线一致（校验结果相同），但 JSON 体积压缩约 80–97%，审查只跑单轮，文献综述采用知识优先 + WebSearch 核实，不为补证据抓取全文。

本目录 `Agent/` 为整理后的唯一副本（原 `Claude/`、`Codex/`、`OpenCode_Aider_Any_Other/` 三份编排副本中，Codex 与 OpenCode 版本均为 Claude 版本的子集或等价物，合并后删除）。`CLAUDE.md`、`AGENTS.md` 等编排提示词与 `.claude/` 配置属于 AI 工作区文件，已随清理移除；本目录保留的是管线功能代码（`Agent/shared/`）。

## 目录内容

| 路径 | 内容 |
|---|---|
| `Agent/shared/evifork_bio_validator.py` | 代数符号网络模拟器（研究扩展 `evifork_bio` 直接调用） |
| `Agent/shared/export_*.py` | 主表 / 补充表 / 图谱导出 |
| `Agent/shared/ode_validator.py`、`rwr_validator.py` | ODE 与随机游走交叉校验 |
| `Agent/shared/scan_gxe.py`、`scan_epistasis.py` | G×E 与上位性扫描 |
| `Agent/shared/provenance/` | 文献溯源（OpenAlex / Europe PMC 检索、句子级定位、物种校验） |
| `Agent/shared/network_to_cytoscape.py` 等 | 网络可视化 / Studio 导出 |
| `Agent/shared/schemas/` | network、evidence、perturbation、provenance、validation 数据模型 |
| `Agent/shared/visual/` | 浏览器可视化（Node 渲染脚本 + HTML 模板） |

## 常用命令

```bash
# 把精选边压缩为 TOON 编码（体积约减 97%）
python EviFork_Bio_Plant/Agent/shared/compact.py --network {trait}_network

# 导出 Cytoscape 文件
python EviFork_Bio_Plant/Agent/shared/network_to_cytoscape.py {trait}_network

# DOI / 证据核查（可写回修复）
python EviFork_Bio_Plant/Agent/shared/verify_evidence.py {trait}_network
```

## 约定

- 每个 `{trait}_network/` 目录携带 network、validation、supplementary 数据；文件使用短键 / TOON 编码，图例见 `Agent/shared/LEXICON.md`。
- 每条边/检验都带真实 DOI（来自检索结果），不虚构。
- 术语与 schema 细节见 `Agent/shared/PIPELINE_REFERENCE.md`。
