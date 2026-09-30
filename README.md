# OnTime Dispatch

**Coordinating Time-Critical Material Delivery: A UAV–AGV Service Concept**

## 最新：功能验证与可复现作品集

2026-09-30 实际完成 **66 项 Python 功能测试，失败 0、skip 0**，另重跑四类算例的 hard / soft 共八组两阶段运行，16 份最终计划由独立 CLI 重算通过。修复了旧 `evaluate_trip` 字典接口允许伪造设备容量的缺陷，以及新增 replan CLI 对非法计划数组处理不当的问题；新增失败测试先实际复现，再修复并重跑。详细已通过、已修复失败和未执行检查见 [docs/validation.md](docs/validation.md)。这些不是用户可用性测试。

[docs/portfolio.md](docs/portfolio.md) 提供输入假设、完整运行命令、源码 / 输入 / 输出 SHA256 与限制。`outputs/portfolio/figures/` 包含来自同一实际记录的路线示意、设备 / 行程时间线、任务结果表、两阶段比较、GA 迭代曲线，以及额外重规划时间线，共 **6 份可编辑 SVG + 6 份清晰 PNG**。中文 Source Han Sans CN、代码 / 标识 Sarasa Mono SC，字体及许可证随项目提供；PNG 展示层使用 Pillow，计算核心仍只有标准库。地图为合成示意布局。

```powershell
.\Run-Validation.cmd
.\Build-Portfolio.cmd --seed 2026 --output-dir outputs/portfolio
```

作品集算例基于固定种子，并新增 T08=60 kg、UAV-02 可用起点 240 s、AGV-02 可用起点 600 s 等演示假设。实际两阶段均分配 7/8 个任务、5 行程，T08 超载未分配；旅行 1183→1178 s，总罚值 13.22→13.12 penalty_unit。较好排列在代 0 初始种群中找到，后续 12 代无进一步改善。没有普遍提升或近似最优声明。

新增 [仓库检查点重规划](docs/replanning.md)：200 s 时模拟 UAV-02 在仓库不可用，保留模拟已完成 T05，固定已开始装载或配送的 T02 / T03 行程，仅调整尚未开始装载的任务；T08 仍未分配。新候选 `approval_status=not_approved`，**不自动等于人工批准或真实执行**。在途故障明确拒绝。CLI：

```powershell
.\Run-OnTime-Python.cmd replan data/portfolio.json outputs/portfolio/ga/plan.json --checkpoint-s 200 --unavailable-vehicle UAV-02 --seed 2026 --output-dir outputs/replan-cli
```

以下保留此前运行记录。旧 Node 界面尚未绑定 Python / GA / 重规划核心。

## 新增：真正衔接的两阶段方法

optimize入口实际运行已有启发式，再把其构造顺序作为GA初始种群index=0；固定解码种子必须还原相同的第一阶段Plan。其余个体由扰动及随机排列生成。解码器按染色体顺序考虑任务，继续完成设备选择、当前行程插入、返仓分趟和时间安排，不重新按deadline排序。

已实现锦标赛选择、排列OX交叉、交换／插入变异、精英保留、最优档案、最大代数及停滞停止。目标先比较未分配数，再比较运输与迟到总代价；每个个体及两阶段最终方案经过独立校验。**未实现2-opt**。编码、解码及约束处理均为2026新增实现，非2025原代码复现。

默认运输系数UAV=0.02、AGV=0.01 penalty_unit/s，旅行含返仓；迟到系数使用任务lateness_cost_per_s，另乘全局无量纲倍率1。均为Illustrative data罚值，不代表实测经济成本。定义及完整CLI参数见[docs/two-stage.md](docs/two-stage.md)。

```powershell
.\Run-OnTime-Python.cmd optimize data/cases/normal.json --mode soft --seed 2026 --population-size 24 --generations 40 --patience 12 --output-dir outputs/ga/normal-soft
```

本次实际种群24、最大40代、精英2、锦标赛3、交叉0.9、变异0.25、patience=12、seed=decoder_seed=2026；成本使用上述默认。2026-09-30用相同四个算例分别运行hard／soft，得到：

| 算例 | 模式 | 未分配：初始→GA | 总代价penalty_unit：初始→GA | 严格改善 | 实际繁殖代数 |
| --- | --- | --- | --- | --- | --- |
| 正常 | hard | 0 → 0 | 12.26 → 12.16 | 是 | 12 |
| 正常 | soft | 0 → 0 | 12.26 → 12.16 | 是 | 12 |
| 超载 | hard | 1 → 1 | 12.26 → 12.16 | 是 | 12 |
| 超载 | soft | 1 → 1 | 12.26 → 12.16 | 是 | 12 |
| 时间窗冲突 | hard | 1 → 1 | 12.12 → 12.12 | 否 | 12 |
| 时间窗冲突 | soft | 0 → 0 | 46.26 → 46.16 | 是 | 12 |
| UAV不可用 | hard | 4 → 4 | 10.44 → 10.44 | 否 | 12 |
| UAV不可用 | soft | 4 → 4 | 10.44 → 10.44 | 否 | 12 |

正常算例两种模式均维持8/8任务、4行程、零迟到；旅行1135→1130 s。较好方案在GA初始种群（代0）已经找到，后续12代没有进一步改善，按停滞条件停止。**不能将此次差额归因为12代进化带来的提升，也不构成普遍性能／近似最优结论。**

hard时间窗冲突仍保留T01未分配，未改善；两种模式的UAV不可用仍保留4个任务未分配，也未改善，实际保留第一阶段原计划。soft时间窗冲突仍有34 s迟到及34 penalty_unit罚值，本次仅运输代价改变。超载T08始终保留未分配，没有以违规分配换覆盖。

[outputs/ga/normal-soft/](outputs/ga/normal-soft/)包含同一输入的[初始计划](outputs/ga/normal-soft/initial/plan.json)、[GA计划](outputs/ga/normal-soft/ga/plan.json)、[逐项比较](outputs/ga/normal-soft/comparison.json)、[逐任务CSV](outputs/ga/normal-soft/task-comparison.csv)、[迭代CSV](outputs/ga/normal-soft/iterations.csv)、初始种群、参数及规范化输入快照。每代从0开始记录当代与累计最优目标、排列及解码／缓存统计。输入SHA256、种子往返证明、实际停止原因保留在run.json。

此前八组运行的两阶段计划共16份，另用evaluate从保存的输入快照重新校核；物理约束均有效。完整实际记录见[outputs/ga/run-record.json](outputs/ga/run-record.json)。没有改善的输出及日志全部保留。该阶段**53项Python测试通过**，覆盖顺序驱动解码、种子真实衔接、排列算子、覆盖优先、最优档案不退化、无改善保留及GA导出校核；最新完整回归见上方66项记录。

以下保留单独schedule入口及此前启发式实际运行记录。optimize和schedule共享同一物理模型；旧Node界面尚未接入Python两阶段核心。

## 2026 Python 调度核心 v2

2025研究源码未找到。Python核心是依据fy01、paper01及spec01–03编写的2026新实现，采用标准库和显式Task、Vehicle、Trip、ScheduledStop、Plan、Evaluation数据结构；不是原源码、严格复现或已部署系统。

已实现JSON加载及字段／单位校验、独立计划校核、完整时间账目、紧迫程度启发式、当前行程所有位置插入和同车多趟。整趟预装载荷、设备适配／可用性、续航及可用时间均为硬约束，返仓必须可行。同车周转后才能开始下一趟；无法安排的任务保留原因和候选证据，不通过违规分配减少未分配数。

默认soft服务开始窗，hard禁止迟到；早到可等待。soft迟到代价=迟到秒×任务显式lateness_cost_per_s，单位penalty_unit（2026演示罚值，非原论文权重或货币）。仅实质评分平局使用局部随机种子；同输入、模式和seed可重复。无可行候选时结束当前尝试。

规则与证据见[docs/model.md](docs/model.md)，CLI与输入解释见[docs/python-project.md](docs/python-project.md)，格式见[docs/input.schema.json](docs/input.schema.json)，合成参数及单位逐项见[docs/scenarios.md](docs/scenarios.md)。

在项目根目录运行（本机Windows入口自动使用Codex随附Python，无需pip安装）：

```powershell
.\Run-OnTime-Python.cmd generate --seed 2026 --output-dir data/cases
.\Run-OnTime-Python.cmd validate data/cases/normal.json
.\Run-OnTime-Python.cmd schedule data/cases/normal.json --mode soft --seed 2026 --output-dir outputs/cases/normal-soft
.\Run-OnTime-Python.cmd evaluate data/cases/normal.json outputs/cases/normal-soft/plan.json --output outputs/cases/normal-soft/checked.json
```

有系统Python时，将命令入口替换为python run_ontime.py即可。--output-dir每次导出plan.json、plan-input.json、trips.csv、stops.csv、legs.csv、unassigned.csv、checks.csv和summary.csv；空CSV仍含表头。--output保留只写JSON的旧接口。部分计划约束有效时退出码仍为0，必须检查complete和unassigned；输入错误／计划违反硬约束退出码2。

## 启发式阶段实际运行记录

2026-09-30，在本机Python 3.12.14上实际运行以下四个输入的两种模式。数据生成种子与调度种子均为2026，一个仓库、8个任务、2台UAV、2台AGV；所有数据标记Illustrative data。以下是实际计划输出，**不代表性能基准、现场效果或最优性结论**。

| 算例 | 模式 | 已安排 | 未分配 | 行程数 | 迟到s | 迟到代价penalty_unit | 计划约束有效 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 正常 | hard | 8 | 0 | 4 | 0 | 0 | true |
| 正常 | soft | 8 | 0 | 4 | 0 | 0 | true |
| 超载 | hard | 7 | 1 | 4 | 0 | 0 | true |
| 超载 | soft | 7 | 1 | 4 | 0 | 0 | true |
| 时间窗冲突 | hard | 7 | 1 | 4 | 0 | 0 | true |
| 时间窗冲突 | soft | 8 | 0 | 4 | 34 | 34 | true |
| UAV不可用 | hard | 4 | 4 | 2 | 0 | 0 | true |
| UAV不可用 | soft | 4 | 4 | 2 | 0 | 0 | true |

正常输入[data/cases/normal.json](data/cases/normal.json)实际得到四个行程、各设备一个，装货均开始于0 s；任务均恰好安排一次。两种模式本次相同，并不意味着soft／hard一般等价。

- [超载](data/cases/overload.json)：T08改60 kg，超过所有设备最大50 kg；两种模式均保留T08为unassigned，主因payload_exceeded。
- [时间窗冲突](data/cases/window_conflict.json)：T01改[0,1] s。hard保留T01为unassigned，主因time_window_conflict；soft保留配送，实际服务开始35 s，迟到34 s、代价34 penalty_unit。
- [设备不可用](data/cases/unavailable.json)：两台UAV设available=false，T01/T03/T05/T07均保留unassigned，主因device_unavailable；没有越过类型适配派给AGV。

八次调度后分别使用evaluate重新计算，均确认所排计划约束有效；部分计划没有被写成任务全集成功。结果在[outputs/cases/](outputs/cases/)，对应目录含plan.json／CSV与checked.json；实际退出码和摘要在[run-record.json](outputs/cases/run-record.json)。CSV和JSON保留单任务时间、整趟装载、返程和周转证据，没有预填成功结论。

复跑全部算例：

```powershell
foreach ($scenarioName in @("normal", "overload", "window_conflict", "unavailable")) {
    foreach ($windowMode in @("hard", "soft")) {
        .\Run-OnTime-Python.cmd schedule "data/cases/$scenarioName.json" --mode $windowMode --seed 2026 --output-dir "outputs/cases/$scenarioName-$windowMode"
        .\Run-OnTime-Python.cmd evaluate "data/cases/$scenarioName.json" "outputs/cases/$scenarioName-$windowMode/plan.json" --output "outputs/cases/$scenarioName-$windowMode/checked.json"
    }
}
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s tests -p "test_*.py" -v
```

此前启发式阶段41项Python测试通过，覆盖插入保护既有窗口、整趟容量、返程续航、等待、装卸／周转、跨趟重叠、重复／遗漏任务、hard／soft、设备适配、种子复现及CSV／JSON导出。测试不作为性能实验。

单独schedule构造基线只测试最后一趟插入及新趟，不做GA；新增optimize在其后搜索任务排列。两者都未实现2-opt、全局最优搜索、共享装货台／工位冲突、真实避障或物理电池仿真。旅行秒矩阵为唯一时间来源，速度字段不会隐式改写矩阵。search_exhaustive=false，搜索未找到候选不证明全局无解。

## 既有Node界面原型

下文使用独立的hard到达窗demo-v1，本阶段未接入新Python模型。

可运行的本地服务原型。依据 Google Drive 的 spec01–03、四页 SVG 及 UAV–AGV 会议摘要实现，使用原生 Node.js + HTML/CSS/JavaScript，无 npm 安装和网络依赖。

## 启动

在本项目目录双击 `Start-OnTime.cmd`，或在 PowerShell 中运行：

```powershell
.\Start-OnTime.cmd
```

打开 <http://127.0.0.1:4317>。终端需保持运行；Ctrl+C 停止服务。启动脚本优先使用 Codex 随附 Node，随后查找系统 Node.js（要求 22+）。有系统 Node 时也可运行 `npm start` 或 `node server.mjs`。

本机已用随附 Node.js 24.19.0 验证。服务只监听 127.0.0.1。可用 `PORT` 更改端口，`ONTIME_DATA_DIR` 指定独立数据目录；同一数据目录仅运行一个服务实例。

## 演示流程

1. **Task Review**：检查任务、车辆载荷／速度／续航／班次／周转和类型专属旅行距离；支持增删改任务及资源、旅行数据编辑。
2. **Generate plan**：产生 Suggested 候选，查看分配、ETA、服务完成、返仓、时间线、示意路线和逐项校核详情。
3. **Plan Review**：Partial 场景包含 T04=25 kg，明确显示超载证据。必须勾选承认未分配任务，再点击 Approve partial plan 并确认。批准不会自动开始。
4. **Start simulation**：进入 Monitor，以 Next event、+1 simulated minute 或 Run to completion 推进事件。普通暂停保留批准。
5. **异常演示**：开始后、推进出发事件前，将 UAV-01 标为不可用。旧批准立即失效，进入 Exception Handling；重排后 T01 无可行到达窗，T02/T03 可保留。
6. 再次承认未分配清单、批准新方案、Resume simulation。结束显示 **Assigned tasks completed; 2 tasks remain unassigned.**
7. Normal 场景只包含 T01–T03，全部服务完成且所有执行行程返仓后才显示 **All tasks completed in simulation.**

保存输入会增加版本、使旧建议和批准失效；运行中保存会暂停并要求重排。已 Delivered 的任务锁定，只能创建新任务提出新的配送需求。运行中异常采用明确标注的 **Simulation rollback**：未完成行程回到仓库检查点重新开始，时钟不倒退，已完成配送不重派。这是教学模拟简化。

## 规则与证据边界

- 固定 `demo-v1`：整数秒、hard arrival、端点包含；服务开始=到达，服务完成可以晚于到达窗上限。
- 每趟一个任务，不拆单；仓库往返，支持同车多趟，周转累计进入车辆日程。
- `travel = ceil(distance / speed)`；延后仓库出发以满足最早到达，完整返程计入续航和班次。
- 新建演示规划器按最早截止时间排序，选最早可行到达的车辆；独立校核器从输入重算时序、载荷、续航、班次、返仓和任务覆盖。
- 标签 **Illustrative data / Proposed extension / Simulation only** 常驻。源码尚未取得：本原型没有复现原研究 GA、2-opt 或多节点合并路线，不宣称最优性、实测准时率、硬件接入或用户研究。

证据读取与实现映射见 [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)。原规格副本、Drive 文件索引、会议摘要提取文本和四页 SVG 位于 `docs/sources/`，供复查。Google Drive 源文件未被修改。

## 保存与导出

输入、方案的不可变快照、批准、事件、交付历史和重置前归档保存到 `data/state.json`。每次成功操作原子写入，API 以 `expected_version` 校验并串行处理写入，避免并发覆盖。重启将 Running 改为 Paused，保留检查点和授权，需手动恢复。损坏的数据文件不会被静默覆盖。

**History** 查看只读历史；**Export record** 导出含输入、版本、计划、批准、事件和归档的 JSON。**Keep tasks unassigned** 记录待办决策，不代表批准或交付。重置演示场景会把现有完整记录保存到归档。

## 验证

```powershell
.\Test-OnTime.cmd
```

或者 `npm test`。14 项自动化测试覆盖 spec03 A01–A12、返仓和周转、缺字段、不可行终止、API 并发冲突、持久化、重启恢复及导出。浏览器已检查部分批准→设备异常→重排→重新批准→恢复→部分完成的完整路径。实际截图在 `artifacts/plan-review.jpg` 和 `artifacts/execution-monitor.jpg`（生成物不纳入版本管理）。

## 主要文件

| 文件 | 职责 |
| --- | --- |
| `src/fixtures.mjs` | spec03 §8 的 Normal / Partial 演示输入 |
| `src/planner.mjs` | 演示规划、原因证据和独立校核 |
| `src/service.mjs` | 快照、版本、批准、任务状态、事件模拟、异常与归档 |
| `server.mjs` | 本地 HTTP API、原子持久化、静态资源 |
| `public/` | 四页界面、编辑弹层、示意图与时间线 |
| `tests/` | 服务契约与真实 HTTP / 重启测试 |

API：GET `/api/state`、`/api/health`、`/api/export`；POST `/api/input`、`/api/plan`、`/api/approve`、`/api/start`、`/api/pause`、`/api/resume`、`/api/advance`、`/api/unavailable`、`/api/keep-unassigned`、`/api/end`、`/api/reset`。所有 POST 使用 JSON 并携带当前 `expected_version`；批准需携带当前 `plan_id`、`snapshot_id` 和完整的 `acknowledged_unassigned` 列表。
