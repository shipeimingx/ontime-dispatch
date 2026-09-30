# OnTime Dispatch：2026 Python 首版模型

版本：`python-demo-2026-v2`；日期：2026-09-30。此项目是依据现有材料和本轮要求编写的 **2026 年新实现**，不是 2025 原源码、严格复现或已部署系统。输入、路线、时间均为计划值；没有设备接入、真实避障或现场性能结论。v2新增显式数据类、当前行程任意位置插入、加权迟到代价、种子控制及JSON／CSV导出；下文时间语义保留v1规定。此文档以本轮用户要求为准。

## 1. 实际阅读与缺失登记

| 材料 | 实际取得／阅读方式 | 本次可用证据与限制 |
| --- | --- | --- |
| [fy01 PPTX](https://drive.google.com/file/d/1ltGBPUj1e6uZa-Poje4708yoM26pzJLE/view) | 2026-09-30 通过 Drive 连接器提取文本；保存 `docs/sources/fy01-text.md` | 提取页16–19：中央仓库、工位、异构设备、多趟、容量、旅行／服务时间、续航／工作时间；21–25：启发式与 GA 方法描述。未把嵌入图片、公式或版面视为已直接阅读 |
| [paper01 PDF](https://drive.google.com/file/d/1Hgax_0xjf6frujkwxfjy2Kne6XLByMg0/view) | 本轮通过 Drive 连接器读取论文文本；本地 `docs/sources/abstract.txt` 保存其文本 | 多趟、异构约束、运输成本加时间违约罚项、两阶段方法；不是完整公式或代码。图注可读不代表图中算法已核实 |
| [spec01](https://drive.google.com/file/d/1DUHDFi5RRJ8LP-RYj5FwBEsETajXDd0j/view) | 已获取全文，本轮阅读本地 `docs/sources/spec01.md` | §4 C01–C06、§5 K01–K12记录来源分歧及待查代码；其中对原图的分析是 spec01 的记录，不冒充本次直接看图 |
| [spec02](https://drive.google.com/file/d/1HlVTxu5oX47YI62i_UOptXGK43u7lskl/view) | 已获取全文，本轮阅读本地 `docs/sources/spec02.md` | 2026 服务提案；任务审阅、方案解释、未分配原因及独立计算检查是新增服务要求 |
| [spec03](https://drive.google.com/file/d/1DevOfRvZyJ2eKwMdZQZxKvdXkg_2PHg6/view) | 已获取全文，本轮阅读本地 `docs/sources/spec03.md` | 原 `demo-v1` 指定 hard 到达窗、单任务一趟等演示规则；本次 Python 采用下文新规则，不能混称同一模型 |
| 2025 UAV–AGV 研究源码 | **未找到，未读取、未执行** | 此前 Drive 目录清单及本地同步材料搜索未找到源码；不推定其他位置不存在。既有 JavaScript 原型是2026新写演示程序，不能当研究源码 |
| 2025 原始实验数据、运行脚本、随机种子、实测矩阵、完整目标函数权重、设备遥测、源码职责记录 | **本次未取得** | 不推导历史运行行为，不采用报告中的性能百分比或 near-optimal 宣称 |

FY01 的30分钟、8小时、速度等只作为其示例文字记录；其续航计时范围不明，**没有自动继承为本项目默认参数**。本项目数据文件内每个设备时限独立显式输入。

## 2. 逐项规则与来源归属

“材料支持”表示概念有文字依据，不表示已验证2025程序实现；“新增”均是2026演示约定。所有下表具体实现由本项目重新编写。

| 编号 | 本版规则 | 归属及证据 |
| --- | --- | --- |
| R01 | 一个仓库、多个工位，路线起终点均为仓库 | 材料支持：fy01 17–19；返程必须纳入可行性检查的明确实现为新增（spec01 K05待查） |
| R02 | UAV／AGV异构，统一选择资源，不同设备可同时配送 | 异构协调概念：fy01 17–19、paper01；统一候选比较和并行日程实现为新增，不沿用旧程序未知分类阈值 |
| R03 | 每任务不可拆分、最多分配一次；完整计划每任务恰好一次；未分配显式保留 | 新增：用户本轮要求；spec01 K03／K10未确认原实现。部分方案不能称任务全集完成 |
| R04 | 一趟可访问多个任务／工位，同设备可多趟；任务只能在仓库预先装载，无中途补货或空地交接 | 多趟：fy01 19、paper01；多站载荷语义及无交接为新增，替代spec03单任务一趟演示 |
| R05 | 出发载荷为整趟需求总和，≤设备容量；每完成一次卸货才减载 | 容量概念：fy01 18；总和／卸载时序为新增，解决spec01 K03缺口 |
| R06 | 正需求kg、适配类型及可选设备ID、available标志、单趟时限、可用时间均为硬约束 | 容量／异构／续航概念：fy01 17–18、paper01；字段、ID适配和硬拒绝规则为新增 |
| R07 | 时间窗限制**服务开始**；端点包含；默认soft，可选hard | **新增演示假设**：本轮要求。fy01严格到达与paper01违约罚项有差异；spec03 hard到达不得推导为本版规则 |
| R08 | 早到在工位等待，迟到=max(0,服务开始−latest)；服务结束可超过latest | **新增演示假设**：本轮要求，解决spec01 K02；hard只拒绝服务开始迟到 |
| R09 | UAV单趟计时=离仓至返仓，含旅行、工位等待、工位卸货及服务、返程 | **新增演示假设**：spec01 K04未确认原范围；本版AGV单趟时限也使用此范围 |
| R10 | 仓库装货、返仓卸货／检查、周转各为输入的固定秒数，全部进入设备日程；不由电量百分比推算续航 | **新增演示假设**：本轮要求、spec01 K04／K06。周转只是固定补给准备时间，不是电池物理模型 |
| R11 | UAV和AGV各用自身旅行秒矩阵，可非对称；null表示该类型不可通行；距离m矩阵可选 | 路径差异概念：fy01 17；矩阵格式、null及不对称为新增。不实现真实障碍物规避，AGV矩阵需外部提供 |
| R12 | 标准单位kg、m、s；时间为同一模拟时基上的非负整数秒；载荷可为小数kg | **新增演示假设**：本轮要求，spec02／03支持内部整数秒。0秒为用户指定的模拟起点，不是日期或UTC |
| R13 | 同车日程不重叠，下一趟装货须等上一趟返仓卸货与周转完成 | 多趟概念：fy01 19；具体时间链为新增 |
| R14 | 可用时间覆盖装货开始至最后返仓卸货结束；周转仅在下一趟出发前必需 | **新增演示假设**：末趟不执行无用途周转，但其next_ready仍展示；不得因此遗漏返仓或卸货 |
| R15 | 单个仓库不限制装货台数量；工位不限制同时服务设备；无交通冲突、动态障碍、故障或中途换车 | **新增演示假设**：研究未给可核实现；本版不同设备并行无需共享资源队列 |
| R16 | 确定性贪心构造；拒绝时列出已检查的候选原因；输出候选计划不等于真实送达 | **新增实现**：spec02 D10及spec03解释／覆盖原则。未实现2025 GA、2-opt、全局最优搜索或现场执行 |
| R17 | v2设备显式提供speed_m_s；核心不以速度覆盖输入旅行秒矩阵，速度只作为描述及合成矩阵的生成参数 | **新增字段及约定**：本轮要求；fy01支持速度概念但没有可核输入接口。v1缺失速度保留None，不猜值 |
| R18 | 每任务迟到代价=迟到秒×lateness_cost_per_s，总代价为各任务相加，单位penalty_unit | **2026新增演示假设**：本轮要求soft计算代价。paper01支持罚项概念，原权重缺失；本项目权重不是原研究权重，也不代表货币 |
| R19 | 任务按deadline／窗口紧迫程度排序；对当前行程所有插入位置及新趟做有限测试；seed仅用于候选实质排序完全相同后的平局 | **2026新增启发式**：本轮要求；无违规分配、无无限重试，不称2025原方法 |
| R20 | schema v2要求显式单位、速度和迟到权重；兼容v1输入；固定种子生成8任务、2UAV、2AGV及三个异常变体 | **2026新增演示数据与接口**：参数逐项见docs/scenarios.md。不是2025原实验或实测矩阵 |
| R21 | 启发式构造顺序作为任务排列种子；种群index=0实际解码为完全相同的第一阶段Plan；其他个体由扰动与随机排列产生 | **2026新增实现**：本轮要求。材料仅支持两阶段概念，2025源码的种群衔接未确认 |
| R22 | 显式排列驱动构造，不重新排序；固定解码种子决定设备、分趟及插入时间；锦标赛／OX／交换与插入变异／精英及停滞停止 | **2026新增编码、解码与GA**，完整定义见docs/two-stage.md；不是原GA复现 |
| R23 | 先最小化未分配数量，再最小化运输与迟到总代价；全程保留最优已知档案，平局保留第一阶段；非法计划不参与适应度 | **2026新增目标及硬约束处理**：本轮要求；原数学权重未取得 |
| R24 | 运输按全部旅行秒（含返仓）×类型系数；UAV0.02、AGV0.01 penalty_unit/s；迟到按任务权重×秒×无量纲beta（默认1） | **2026演示系数**，非经济成本／原研究权重。等待／服务及仓库过程的经济系数为0，但完整计入时间约束 |
| R25 | 每个新个体和最终两阶段方案都经独立校核；保存代0及各代最优、参数、输入快照、比较和未改善结果 | **2026新增验证与输出**：本轮要求；单个固定算例结果不是普遍性能证据 |
| R26 | 本次没有实现2-opt，仍无全局最优／近似最优声明 | 原材料提到2-opt不证明当前实现；本次只实现排列GA及已有构造插入 |

## 3. 变量、时间账目与约束

节点0代表输入指定仓库d，其余为工位。任务i有需求q_i kg、工位n_i、窗口[e_i,l_i] s、卸货u_i s、服务p_i s、迟到权重λ_i penalty_unit/s、允许设备类型集合，可选允许设备ID集合。设备k有容量Q_k kg、类型、速度v_k m/s、显式单趟时限E_k s、可用区间[A_k,B_k] s、装货L_k s、返仓卸货／检查U_k s、周转C_k s。

类型v的有向旅行矩阵T_v(a,b)单位s，不从速度或几何距离隐式生成；null边禁止通行。同类型设备共用该矩阵是新增简化，若有设备专属速度须外部生成新模型数据／扩展格式。

一趟装载任务序列(i1,…,ir)，r≥1。容量在出发前检查：Σq_i≤Q_k，而不是只检查各任务或当前剩余载荷。任务完成卸货后从载荷中减去q_i；不接受重复任务。

设装货开始h，离仓D=h+L_k。第一站前序时间为D、节点为d；对每站：

```text
arrival_i       = previous_completion + T_type(previous_node, n_i)
waiting_i       = max(0, e_i - arrival_i)
service_start_i = arrival_i + waiting_i
unload_end_i    = service_start_i + u_i
completion_i   = unload_end_i + p_i
lateness_i     = max(0, service_start_i - l_i)
lateness_cost_i = lateness_i * lateness_cost_per_s_i
total_lateness_cost = sum(lateness_cost_i)
```

本版“服务开始”指**工位卸货开始**，工位卸货与随后服务合计占用u_i+p_i；service_s不再次包含unload_s。允许同一工位多个不同任务顺序服务，不合并成一个任务。early arrival等工位等待，装货前因设备时间链产生的仓库等待另外记账。

```text
return_s          = last_completion + T_type(last_node, depot)
mission_s         = return_s - departure_s
depot_unload_end_s = return_s + depot_unload_s
next_ready_s      = depot_unload_end_s + turnaround_s
```

硬校核：available=true；每任务适配；Σq_i≤Q_k；所有路线边可通行；mission_s≤trip_limit_s；h≥available_from_s且h≥上一趟next_ready_s；depot_unload_end_s≤available_until_s；hard模式另要求所有lateness_i=0。时限相等可接受。soft仅放宽latest，不放宽容量、适配、续航、可用时间，也不允许在earliest前开始服务。

**续航钟**包括离仓之后全部工位等待、卸货、服务和往返旅行；不包括离仓前仓库等待／装货、返仓后卸货／周转。可用时间检查则包括上述仓库过程及两趟间隔。充电是否真正恢复电量不模拟；每趟重新得到相同输入时长预算是新增假设，禁止把该预算解释为电池实时估计。仓库返程空载，但固定卸货／检查段仍保留。

设备利用的计划时间跨度可从首趟装货至末趟仓库卸货结束计算；本版不输出效率提升百分比。距离矩阵只用于选定路线的距离汇总，不能代替旅行时间，不用于真实导航。

## 4. 首版求解与输出边界

这是有限终止的构造基线。任务按(latest, latest−earliest, earliest, task_id)排序；较早截止优先，同截止时较窄窗优先。对于每个任务，对每台设备测试①在该设备当前最后一趟的0到r位置插入②在其next_ready后新建一趟。每个候选重算所有站点的时间、整趟载荷、返程及可用时间，既有站点也必须保持hard可行。只接受完整路线校核通过的候选；按(新增迟到代价, 新增旅行秒, 本任务服务开始秒, 是否新趟)字典序选择，最后用局部Random(seed)平局。同输入、模式、seed可重复；seed不降低约束。

该排序是**2026新增启发式偏好**，不是paper01运输成本＋罚函数的数学复现：原权重缺失，新增演示权重不代表货币／能耗目标。只插入当前最后一趟，保持原有任务之间的相对顺序；不修改更早行程或换设备，不搜索延迟离仓以降低工位等待。因此搜索没找到方案不能证明全局不可行。输出`search_exhaustive=false`及未分配候选证据。每任务最多测试Σ_k(当前行程任务数+2)个候选后前进，不存在无可行候选时的重试循环。

计划输出：profile、mode、所有行程的载荷／旅行／等待／卸货／服务／返程／周转时间账目、每任务服务开始和迟到、各项检查、assigned／unassigned清单和Complete／Partial／No assignment覆盖标签。`planned`含义只表示已排入计划，不能写Delivered。所有输入任务须在assigned或unassigned恰好出现一次。

独立`evaluate`／`check_plan`不调用启发式，不信任导出计划的ETA、valid或summary，而由输入矩阵及简洁行程重新计算。检查跨趟时间链、同趟／跨趟任务唯一性、未分配唯一性、assigned与unassigned互斥、每个输入任务有归属；hard违约报告无效，不静默改路线。手写仅trips的旧格式会显式补记缺失任务为not_in_plan；带unassigned的格式若静默遗漏任务则校核失败。`valid`与`complete`分别表达约束和覆盖。

数据类：Task、Vehicle、Problem、Trip、ScheduledStop、Plan、Evaluation（另有Check、TravelLeg、TripEvaluation、UnassignedTask）。`load_instance`加载为Problem；`construct_plan`返回Plan；`check_plan`返回Evaluation。旧字典入口load_problem／schedule／evaluate_plan保留兼容。

### 4.1 已接入的两阶段方法

`optimize`首先实际运行上述启发式，再以其构造顺序为首个染色体搜索；`schedule`仍只运行第一阶段。解码使用显式task_order，不重做紧迫程度排序。每个染色体涵盖全部任务，包括种子计划未分配的任务；候选仍受R01–R20的物理规则约束。

GA目标为字典序`(unassigned_count, transport_cost + lateness_penalty)`。运输=Σ类型系数×行程旅行秒；迟到=beta×Σ任务lateness_cost_per_s×迟到秒。默认UAV／AGV系数0.02／0.01 penalty_unit/s，beta=1。全部为演示成本，非实测经济成本。独立校核先于适应度；最优档案不得比第一阶段差。具体算子、停止条件、初始种群证明、代0含义与实际结果见[docs/two-stage.md](two-stage.md)。物理profile仍为python-demo-2026-v2，新方法profile为two-stage-permutation-ga-2026-v1；两者含义不同。

## 5. 输入、目录及运行

输入结构定义见 `docs/input.schema.json`，运行说明见 `docs/python-project.md`，逐项参数见 `docs/scenarios.md`。`data/cases/`为schema v2固定种子Illustrative data；旧`data/demo_2026.json`为v1样例。v1缺失速度为None、缺失迟到权重采用本项目新增默认1 penalty_unit/s，均不作为历史事实。v2要求units、speed_m_s、lateness_cost_per_s显式输入。不识别的字段拒绝，禁止电量百分比／分钟误作时长秒。JSON／CSV均只保存计划结果，无设备执行动作。

```text
src/ontime/              models/input/evaluate/scheduler/ga/export/generate及CLI
data/cases/             固定种子正常、超载、时间窗冲突、不可用算例
data/demo_2026.json      2026演示输入（非2025实验数据）
tests/test_ontime.py     模型边界和跨趟检查
docs/model.md           本文；证据、规则归属、公式和限制
docs/input.schema.json  输入JSON结构
docs/python-project.md  运行命令及输出解释
docs/scenarios.md       参数单位、合成假设及异常变更
docs/two-stage.md       2026排列GA、衔接、代价、算子与停止条件
docs/sources/           实际读取材料文本与原有来源登记
outputs/                运行生成的计划（不作为性能实验）
run_ontime.py           无安装运行入口
Run-OnTime-Python.cmd   Windows标准库启动入口
```

既有Node服务和src/*.mjs属于独立的旧`demo-v1`界面演示；本阶段没有把它绑定到新Python模型，也不改变它的历史输入状态。新核心可以作为以后服务适配的基础。

## 6. 功能验证、作品集及检查点扩展

`docs/validation.md` 保存本次实际执行与修复记录；功能测试不等于用户可用性测试。`docs/portfolio.md` 和 `data/portfolio.json` 定义单次合成演示与可复现 SVG / PNG，所有图形以保存的运行结果为依据。

以下规则均是 **2026 新增扩展假设，原材料未支持这些具体异常恢复语义**：仓库检查点模拟设备不可用；完成时间不晚于检查点的任务保留；装载严格早于事件的行程整体冻结，已装载未完成任务不移车；其他未完成 / 未分配任务才进入剩余问题的启发式 + GA；新装载起点受检查点、原可用起点及冻结行程仓库周转约束；故障设备不接受新行程；事件与装载同秒时，事件先发生。

历史使用原参数独立重算，未来使用事件后的剩余输入独立重算，另验证冻结记录及时间事件。对在途故障不支持恢复并明确拒绝，不虚构返仓或货物转移。执行记录只是基线时钟模拟，没有硬件遥测。重规划仍为待人工批准候选，`not_approved` 不自动变为执行许可。完整边界与命令见 [replanning.md](replanning.md)。
