# 可复现的作品集素材

本交付是 2026 新 Python 实现的功能验证与合成演示。2025 UAV–AGV 研究源码未找到；不称为原源码、严格复现、已部署系统、普遍性能提升或原研究指标验证。原材料阅读范围及规则来源继续见 [model.md](model.md) 和 sources 目录。

## 单次记录与输入假设

五类要求的图形均读取 `outputs/portfolio/run.json` 的同一记录，不手填不同运行的数字。额外第六张展示该记录的 GA 计划在设备不可用事件后的新候选。`manifest.json` 保留核心源码 SHA256、输入 SHA256、完整重复运行相等检查及输出文件摘要；`figure-manifest.json` 记录图形、字体摘要与来源。时钟秒数全部相对场景起点，不是实时时刻。

输入 `data/portfolio.json` 由 `scripts/build_portfolio.py` 的固定种子 2026 生成：一个仓库、8 任务、2 UAV、2 AGV。基本字段、kg / m / s 单位、设备容量、速度、续航范围、仓库装卸 / 周转、任务服务时间与合成矩阵逐项说明见 [scenarios.md](scenarios.md)。以下三项改变和异常事件均为 **2026 新增演示假设**，不来自原研究测量：

| 参数 | 数值 / 单位 | 目的 |
| --- | --- | --- |
| T08 预装重量 | 60 kg | 明确触发超过最大可用容量 50 kg，保留未分配原因 |
| UAV-02 可用起点 | 240 s | 在仓库等待，200 s 时允许模拟设备不可用 |
| AGV-02 可用起点 | 600 s | 展示不同可用时间及仍未装载的可调整行程 |
| 检查点 | 200 s | 根据基线计划模拟已完成 / 已执行部分 |
| 不可用设备 | UAV-02 | 仅示范仓库故障，不处理在途救援 |

默认 soft、服务开始时间窗、提前到达等待、时间和成本定义仍是 [model.md](model.md) 中声明的演示假设。UAV 每趟计时从装载后出发到返仓，包含工位等待、卸载与服务；仓库装载 / 卸载 / 周转另计可用时间及同车下一趟起点。不由电量百分比换算分钟。示意路线不是真实工厂地图，不是障碍物规划结果。

运行参数：种群 24、最大繁殖 40 代、精英 2、锦标赛 3、OX 交叉率 0.9、交换 / 插入变异率 0.25、停滞 patience 12、搜索与解码 seed 2026。运输系数 UAV 0.02 / AGV 0.01 penalty_unit/s，覆盖所有旅行边含返仓；任务迟到系数使用输入 penalty_unit/s，全局倍率 1。均为演示罚值，无货币或实测经济解释；没有 2-opt。

## 此次实际结果

| 指标 | 启发式 | GA |
| --- | --- | --- |
| 已分配 / 未分配任务数 | 7 / 1 | 7 / 1 |
| 行程数 | 5 | 5 |
| 旅行时间（含返仓） | 1183 s | 1178 s |
| 工位等待 / 迟到 | 0 / 0 s | 0 / 0 s |
| 总罚值 | 13.22 penalty_unit | 13.12 penalty_unit |

T08 超载始终未分配。较好排列在 GA 代 0 初始种群中找到，之后实际繁殖 12 代没有进一步改善，按停滞条件停止。曲线保留所有 13 个点，没有伪造连续改善。以上仅描述这一个输入、参数、种子和模式。

检查点演示保留模拟已完成的 T05；冻结已开始的 T02 / T03 行程及剩余部分（T02 在配送途中，T03 仍在装载）。T01 / T07 从尚未装载的 UAV-02 行程移至 UAV-01 的新行程，最早 326 s 装载；AGV-02 尚未装载的访问顺序也允许调整。T08 仍超载未分配。历史 / 剩余问题 / 时间事件独立检查通过，**新候选未经人工批准**。详见 [replanning.md](replanning.md) 及 `replan/task-state.csv`。

## 图形与结果文件

| 图形 | 可编辑 SVG | 高清 PNG |
| --- | --- | --- |
| 仓库与工位示意路线 | [01-routes.svg](../outputs/portfolio/figures/01-routes.svg) | [01-routes.png](../outputs/portfolio/figures/01-routes.png) |
| 设备 / 行程时间线 | [02-timeline.svg](../outputs/portfolio/figures/02-timeline.svg) | [02-timeline.png](../outputs/portfolio/figures/02-timeline.png) |
| 任务分配与时间窗 / 未分配原因 | [03-task-table.svg](../outputs/portfolio/figures/03-task-table.svg) | [03-task-table.png](../outputs/portfolio/figures/03-task-table.png) |
| 同算例两阶段比较 | [04-comparison.svg](../outputs/portfolio/figures/04-comparison.svg) | [04-comparison.png](../outputs/portfolio/figures/04-comparison.png) |
| GA 迭代曲线 | [05-ga-iterations.svg](../outputs/portfolio/figures/05-ga-iterations.svg) | [05-ga-iterations.png](../outputs/portfolio/figures/05-ga-iterations.png) |
| 异常后固定历史 / 新候选 | [06-replan-timeline.svg](../outputs/portfolio/figures/06-replan-timeline.svg) | [06-replan-timeline.png](../outputs/portfolio/figures/06-replan-timeline.png) |

JSON / CSV 输出包含 initial、ga 的方案与逐项独立 checks，comparison、task-comparison、iterations、initial-population、parameters、input-snapshot，以及 replan 的剩余输入、两阶段剩余计划、冻结片段、task-state.csv 与合并结果。UTF-8 BOM CSV 适合在 Excel 查看；秒数和数值以文件为准。

SVG 保留可编辑 `<text>`、路径 / 线段、矩形和圆形。中文为 **Source Han Sans CN**，参数与代码标识为 **Sarasa Mono SC**；不使用 DejaVu Sans。字体文件及许可证随 `assets/fonts/` 和图形旁的 `fonts/` 提供。渲染脚本用 Pillow 直接加载这两个文件，并检查字体族名，禁止静默回退。PNG 以相同绘图数据生成 2 倍像素尺寸，带 300 dpi 元数据。

字体来源：[Adobe Source Han Sans 2.005R](https://github.com/adobe-fonts/source-han-sans/tree/2.005R/SubsetOTF/CN)、[Sarasa Gothic 1.0.41](https://github.com/be5invis/Sarasa-Gothic/releases/tag/v1.0.41)。实际文件 SHA256 见 `assets/fonts/provenance.json`。编辑器可能忽略 SVG 的相对 @font-face；若编辑时字体不匹配，应加载随附字体。未实际验证第三方矢量编辑器的编辑 / 再导出流程。

## 运行命令与依赖

在项目根目录执行：

```powershell
.\Run-Validation.cmd
.\Build-Portfolio.cmd --seed 2026 --output-dir outputs/portfolio
.\Run-OnTime-Python.cmd evaluate data/portfolio.json outputs/portfolio/ga/plan.json --output outputs/portfolio/ga/checked-cli.json
.\Run-OnTime-Python.cmd replan data/portfolio.json outputs/portfolio/ga/plan.json --checkpoint-s 200 --unavailable-vehicle UAV-02 --seed 2026 --output-dir outputs/replan-cli
```

图形 / 文件摘要及重规划独立事件门可另执行 `python scripts/verify_portfolio.py outputs/portfolio --output-file outputs/validation/portfolio-check.json` 检查。当前已实际检查六组 SVG XML、PNG 可读性 / 尺寸、指定字体族、输入摘要、输出摘要和历史 / 未来校验；六张 PNG 已逐张目视检查。第三方 SVG 编辑器编辑 / 再导出未执行。

`python scripts/package_portfolio.py` 将 Python 源码、测试、输入、实际输出、图形、字体与文档打包为 `outputs/delivery/ontime-dispatch-2026-portfolio.zip`，并校验压缩包 CRC。压缩包仅交付 Python 项目；不包含旧 Node 界面、`data/state.json`、研究原始二进制文件或未找到的 2025 源码。README 保留的旧 Node 使用记录不表示该界面包含在此 Python 包中。

三个 cmd 包装器优先使用本机 Codex 随附 Python，否则使用系统 Python。跨平台对应 `python scripts/run_validation.py`、`python scripts/build_portfolio.py --seed 2026 --output-dir outputs/portfolio` 和 `python run_ontime.py ...`。Python 3.12+；调度、GA、重规划、验证核心只有标准库。仅 PNG 展示层依赖 Pillow，本次实际版本 12.3.0，见 `requirements-presentation.txt`。另一个环境可安装该文件，字体随交付提供，无需全局安装。

`--no-figures` 可仅生成可复现数据及重规划输出；不宣称生成了图形。输入数据种子、搜索参数、字体 / 源码摘要均保存，完整固定种子搜索记录已实际重复比较。不同 Pillow / FreeType 版本可能带来 PNG 抗锯齿差异，不影响调度数值复现。

## 验证范围与限制

功能结果见 [validation.md](validation.md)。本次检查覆盖输入、约束、计划完整性、两阶段衔接、种子与检查点重规划；没有用户可用性测试。未验证真实工厂地图、真实经济成本、硬件配送、遥测、碰撞规避、真实充电、在途故障救援、审批控制或生产部署。旧 Node 演示界面尚未接入此 Python / GA / 重规划核心。
