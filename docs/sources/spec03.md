# spec03界面与交互规格

OnTime Dispatch｜v1.0｜2026-09-30  
**Proposed extension** · **Illustrative data**  
基线：[spec01](https://drive.google.com/file/d/1DUHDFi5RRJ8LP-RYj5FwBEsETajXDd0j/view)及spec02。四页SVG为低保真设计产物，没有真实系统、个人独立开发或用户测试声明。

## 1. 视觉、页面骨架与编辑资产

已读取当前port04作品集排版母版v1.0.pptx的18–23页，样式与颜色来自实际文件。四页均采用横向1440×1000 SVG画布，原生文字／矩形／线路可编辑，无位图截图。

| 项目 | 规格 |
| --- | --- |
| 背景／正文／配送强调 | #FAFAF7／#182936／#3463A7（port04当前配色） |
| 次级文字／表面 | #5C6C75／#FFFFFF；新增浅蓝#EDF3FA、边线#D6DDE2 |
| 警告／错误 | 新增#8A5A14／#A33D32；同时显示文字、图标或边框，不只用颜色 |
| 字体 | Source Han Sans SC优先；Source Han Sans CN、Noto Sans CJK SC、sans-serif回退；不转路径以保留可编辑性 |
| 信息密度 | 标题28–32，表格14–16，关键状态16–18；一行文案优先；字段长文本用详情面板或换行 |
| 全局壳 | 品牌、Proposed extension、四页导航、输入版本／plan ID／simulation标记；底部Illustrative data |
| 导航 | 页面名称不代表状态推进；点Monitor无有效批准时显示未运行，不自动开始 |
| 辅助图 | 示意路线图和时间线；不可冒充实际地图或位置遥测；表格含同等信息 |
| 可用性 | 后续实现要求键盘访问、可见焦点、错误关联字段、状态文字；SVG当前仅示意布局，不包含交互程序 |

文件：ui01TaskReview.svg、ui02PlanReview.svg、ui03ExecutionMonitor.svg、ui04ExceptionHandling.svg。图中数据由本稿§8的算例脚本复算并填入；仍属于Illustrative data，不是调度源码执行结果。

## 2. 状态、版本和批准契约（本次P）

状态用三个维度，避免把Approved误作Delivered：

| 对象 | 状态 | 含义 |
| --- | --- | --- |
| 输入 | Draft / Valid / Invalid | Valid只表示格式及配置可计算，不保证可分配 |
| 候选方案 | Calculating / Suggested / Stale / Calculation failed | Suggested含Complete或Partial覆盖标记；零分配结果另为No feasible assignment found |
| 批准 | Not approved / Approved / Invalidated | 仅Approved且绑定当前快照才能启动／恢复 |
| 模拟 | Not started / Running / Paused / Needs replan / Finished / Failed | Finished另标全部完成或部分完成；不是任务全集成功的同义词 |
| 任务 | Unplanned / Assigned / Unassigned / Waiting / Travelling / Serving / Delivered / Interrupted | Unassigned有原因；Delivered在本次模拟的服务完成事件产生；Interrupted待重排 |

### 2.1 绑定与失效

一个计算快照包含tasks、vehicles、travel matrix、rule profile、模拟时刻、已完成任务及仓库检查点。以input_revision、runtime_revision及snapshot_id标识；plan ID绑定该snapshot ID；approval记录plan ID、snapshot ID、批准任务集、承认的未分配清单及模拟操作者标签。匿名演示标签不是身份认证。

保存影响计算的字段变更、增删任务、修改窗口、载荷、服务时间、车辆能力／可用性、旅行时间或规则→input_revision增加；旧Suggested成为Stale，旧approval成为Invalidated，活动批准清空。编辑草稿期间禁用批准／启动；取消草稿且未保存、未改变运行状态时可回原快照。纯页面排序、打开详情不改变输入。

运行中的到达／完成事件增加runtime_revision。它们是原批准计划预期的事件，不自动作废本次运行授权；但审批中的新候选若检查点已变化必须拒绝批准。实际批准／启动／恢复都原子检查快照与资源，不能只禁用前端按钮。异常或运行中输入修改则立即暂停、使活动批准失效并增加新快照，历史方案和事件不删除。

计算请求携带快照ID；返回结果与当前ID不一致时只保留为历史，不进入Suggested，不恢复旧批准。重复点击批准／开始应幂等，不能产生两次模拟运行。批准部分方案必须显式承认未分配任务；零Assigned时禁止批准。

### 2.2 状态转换与页面跳转

| 触发 | 状态变化 | 跳转／界面结果 |
| --- | --- | --- |
| Save valid tasks | 输入Valid；若已有计划则Stale、批准Invalidated | 留Task Review；提示需重算 |
| Generate plan | Calculating→Suggested Complete／Partial，或零分配／Failed | Plan Review；计算期间显示进度状态，不显示编造ETA |
| Approve plan / Approve partial plan | 当前Suggested＋校核通过→Approved | 留Plan Review；显示批准范围，启用Start simulation |
| Start simulation | 当前有效Approved→Running | Execution Monitor |
| Pause simulation | Running→Paused；原批准仍有效，前提是没有计算输入变更 | 留Monitor；普通暂停可Resume，无须新批准 |
| Mark device unavailable / Save changed window | 暂停；旧候选Stale、批准Invalidated；Needs replan | Exception Handling，显示影响及检查点 |
| Replan remaining tasks | 新快照→新Suggested | Plan Review；必须重新批准，Resume simulation才启用 |
| 零分配／失败 | 没有可批准候选；所有剩余任务有理由或计算错误 | 保留Plan Review或回Exception Handling；可编辑输入、保留未分配、结束未完成模拟 |
| 全部执行任务完成且返仓 | Finished | 全集Delivered显示全完成，否则显示未分配数量；查看详情不触发重派 |

## 3. 四页逐页规格

### 3.1 Task Review

主要问题：任务和资源要求是否完整、是否按明确的规则计算？支持spec02 D01、D04、D10。

| 区域／字段 | 规则及英文文案 |
| --- | --- |
| 页头 | Task Review · Check requests before planning.；Input r1；Simulation only |
| 任务表 | Task、Station、Load (kg)、Arrival window、Service (min)、Vehicle eligibility、Input check |
| 任务详情 | 稳定task_id、station_id；单任务需求kg>0，服务秒≥0，earliest≤latest；本次同一模拟日时钟，内部整数秒；目的地必须存在旅行时间矩阵 |
| 设备卡 | Vehicle、Type、Availability、Capacity (kg)、Speed (m/s)、Trip limit (min)、Shift limit (min)、Turnaround (min)；数值为演示配置 |
| 计算规则 | Window event: Arrival；Policy: Hard；Depot return: Required；Profile: demo-v1；规则未知时不可规划 |
| 主要动作 | Add task / Edit task / Save changes / Generate plan；有未保存编辑时显示Save changes，禁用Generate |
| 次级动作 | Reset illustrative scenario（确认后重置，清楚说明运行记录另存历史）；Review history |
| 页面状态 | Empty、Editing、Invalid、Ready；Ready仅可计算，不表示全部可行 |
| 错误 | Enter a load greater than 0 kg. / End time must not precede start time. / Travel time is missing for this station. / Save or discard your changes before planning. |
| 修改警示 | Saving these changes invalidates the current plan and approval. |
| 跳转 | Generate→Plan Review；查看旧计划→只读Plan Review历史态；运行中保存变更→Exception Handling |

T04载荷25 kg虽超过当前所有设备容量，仍是Valid输入；不得把“无可行资源”当格式错误阻止其他任务规划。Generate后才显示Unassigned: exceeds available payload。输入非法与任务不可行要分开。

### 3.2 Plan Review

主要问题：候选计划是什么、ETA怎样计算、哪些任务不能分配、是否值得批准模拟执行？支持D02、D03、D05、D06、D10。

| 区域／字段 | 规则及英文文案 |
| --- | --- |
| 页头及摘要 | Plan Review · Inspect the candidate before approval.；Plan P01、Input r1、Suggested / Partial；3 assigned · 1 unassigned（SVG示例） |
| 任务表 | Task、Vehicle / Trip、Arrival window、ETA、Service end、Window check、Assignment；未分配ETA用“—”，不能填候选测试时间当正式ETA |
| 详情抽屉 | Depart、Travel time、Arrive、Service start、Service end、Return to depot、Trip duration、Payload check、Endurance / Shift check、rule profile、未舍入秒值 |
| 路线图 | 示意Depot→Station→Depot；显示vehicle／trip，与表格关联；无真实地理坐标声明 |
| 时间线 | 出发、行驶、服务、返程、补给段；时间窗带及event label；ETA由计算器提供，不由UI按颜色猜测 |
| 未分配面板 | Task＋reason_code＋简洁解释＋相关计算证据＋可操作下一步；若多个限制均失败，保留全部已核原因并说明主因规则 |
| 主要动作 | Approve plan；Partial用Approve partial plan，并勾选“I acknowledge 1 unassigned task.”；批准弹层重复展示范围及模拟标识 |
| 批准后 | Approved for simulation；Start simulation（初次）或Resume simulation（异常后）；不自动开始 |
| 次级动作 | Edit inputs→Task Review；View exception→Exception Handling；Keep tasks unassigned仅保存待办，不是批准或完成 |
| 错误 | Plan is out of date. Recalculate before approval. / No assigned tasks to approve. / Calculation failed. No new plan was created. / Acknowledge the unassigned tasks to continue. |
| 空结果 | No feasible assignment found for the remaining tasks.；显示规则证据或Search did not find an assignment，允许保留未分配，不显示成功 |
| 跳转 | 批准留当前页；启动／恢复→Monitor；返回异常不改变候选批准状态；未保存修改禁用批准 |

Window check=Within window / Outside window / Not evaluated。hard窗不满足的任务不进入Assigned。soft／mixed配置未来若接入须另显示penalty和hard-limit check；本次demo-v1不提供无根据罚分。

### 3.3 Execution Monitor

主要问题：哪个批准方案正在模拟、任务处于哪个阶段、是否需要暂停处理变化？支持D03、D07、D09、D11。

| 区域／字段 | 规则及英文文案 |
| --- | --- |
| 页头 | Execution Monitor · Follow the approved simulation.；Simulation time；Run ID；Plan ID；Approved snapshot |
| 状态摘要 | Running／Paused／Needs replan；Delivered / total、Assigned not delivered、Unassigned；总数以纳入任务集为分母，无准时率百分比 |
| 设备表 | Vehicle、Availability、Simulation state、Task / Trip、Next event；无真实电池百分比／GPS |
| 任务表 | Task、Vehicle、Scheduled ETA、Simulated arrival、Simulated service end、Status；预估与模拟事件实值分列 |
| 时间线／事件 | departure、arrival、service completed、returned、device unavailable；实际指模拟事件，不写real-time |
| 主要动作 | Pause simulation / Resume simulation；恢复仅在当前批准有效时，否则View exception |
| 异常注入 | Mark device unavailable（选择设备，显示影响后确认）；Change task window→Task Review编辑，仅保存后变更生效 |
| 非运行态 | No approved simulation is running. Review and approve a plan first.；按钮Review plan |
| 错误 | Approval is no longer valid. Review a new plan before resuming. / Simulation stopped unexpectedly. Last checkpoint preserved. |
| 完成态 | All tasks completed in simulation. 或 Assigned tasks completed; 1 task remains unassigned.；不是All deliveries successful |
| 跳转 | 设备不可用／保存窗口修改→Exception Handling；查看计划→Plan Review只读当前批准；暂停不自动重排 |

SVG展示09:00异常事件后Needs replan的监控态，并用原计划时间线作只读对照，必须标“Previous approved plan · now invalid”。不是在失效后继续执行。

### 3.4 Exception Handling

主要问题：发生什么、谁受影响、哪些决定失效、下一步可执行什么？支持D04–D08、D11–D12。

| 区域／字段 | 规则及英文文案 |
| --- | --- |
| 页头 | Exception Handling · Review the change and replan.；Simulation paused；Input r2；Old approval invalidated |
| 变更卡 | Event ID、Simulation time、Device或Task、Before / After、Reason；本次示例UAV-01 Available→Unavailable |
| 影响表 | Task、Old assignment / ETA、New suggestion / ETA（仅已计算）、Change / Reason；未分配正式ETA“—” |
| 检查点 | 已完成任务只读；剩余任务列表；运行中回滚未完成行程显示Simulation rollback: restart from the last depot checkpoint.；不隐瞒模拟简化 |
| 主要动作 | Replan remaining tasks；已有新建议时Review new plan→Plan Review；该页不能直接批准／恢复 |
| 次级动作 | Edit inputs、Keep tasks unassigned、End simulation with unfinished tasks（确认，保存状态；不称成功） |
| 新方案提示 | New plan requires approval.；原审批记录可查看，不可恢复为活动批准 |
| 无方案态 | No feasible assignment found. Unassigned tasks are preserved.；保留原因、任务及检查点，只有编辑／保留／结束动作 |
| 失败态 | Replanning failed. No new plan was created.；旧建议仍失效，Retry replan不复用旧批准 |
| 窗口变化态 | Changed window: 09:03–09:07 → 09:03–09:03；显示字段校验和计算后的影响；不能仅改界面窗口标签不重算 |
| 跳转 | Review new plan→Plan Review，新Suggested；Edit inputs→Task Review；新批准后由Plan Review恢复→Monitor |

## 4. 数据契约与字段来源（P，不是已知旧API）

| 对象 | 拟议必要字段 | 生成责任／来源 |
| --- | --- | --- |
| Input snapshot | id、input_revision、tasks、vehicles、travel_seconds、rule_profile_id、runtime_checkpoint | 原型输入；概念来自spec01 S03–S08，键名全部新增 |
| Task | id、station、load_kg、window_start_s、window_end_s、service_s、eligible_types | 人工录入／演示fixture；格式校验 |
| Vehicle | id、type、available、capacity_kg、trip_limit_s、shift_end_s、turnaround_s、depot_checkpoint | 原型配置；不要以此声称实测规格 |
| Candidate | plan_id、snapshot_id、coverage、assignments、unassigned、checks、calculation_status | 规划器＋独立校核；Calculated仅在结果通过结构校核后显示 |
| Assignment | task_id、vehicle_id、trip_id、depart_s、arrival_s、service_start_s、service_end_s、return_s、window_check、payload_check、trip_check、shift_check | 计算器；UI仅格式化时刻，不生成可行性 |
| Unassigned | task_id、reason_codes、explanation、evidence、next_actions | 校核证据或搜索诊断；没有证据不能用“payload exceeded”等具体原因 |
| Approval | approval_id、plan_id、snapshot_id、approved_task_ids、acknowledged_unassigned、actor_label、recorded_sim_time、status | 明确人工批准；actor_label不是已验证个人身份 |
| Simulation / Event | run_id、plan_id、clock_s、checkpoint、task_state、event_id、event_type、event_time、affected_ids、message | 模拟器；与预测时间分别存储；本阶段未实现 |

UI不得默认为旧代码具备上述字段。适配未知旧代码需先完成spec01 K11；缺失字段应标Not available并阻止依赖它的批准校核，而非补零或固定成功状态。

## 5. 计算语义与未分配原因

### 5.1 本次演示profile demo-v1

此规则由本次设计提出，非原研究复现，待Peiming讨论记录R01、R04、R08。此profile只定义可行性和时序校核，不定义运输成本权重、违约罚项或最优性指标。单任务单趟，支持同一车辆串行多趟；不拆单、不空地接力。全部从仓库出发并返回；预先定义设备各自旅行时间矩阵，SVG路线仅示意。旅行秒值用distance/speed向上取整；演示往返对称。

时间窗为**hard arrival**，含端点：e≤arrival≤l；不通过就不分配。可以在仓库延后出发，使到达不早于e，不能把“早到后等待”冒充到达窗满足。服务开始=到达，完成=到达+service；服务完成可以晚于l，因为这是到达窗。后续切换事件语义必须变更profile、失效旧计划并重新计算。

对车辆k任务i：travel=ceil(distance/speed)，depart=max(vehicle_ready, e−travel)，arrival=depart+travel，service_end=arrival+service，return=service_end+return_travel，trip_duration=return−depart；trip_duration≤trip_limit，return≤shift_end，load≤capacity。下一趟ready=return+turnaround；仓库等待和周转累计进入班次日程，trip限只覆盖本趟出发至返仓。载荷整趟取单任务重量，返仓再补给；不宣称物理电池模型或真实充电行为。

后续多节点行程须改为整趟初始需求和≤容量、沿途卸货减载，并计算每段服务／等待／返程；本次不实现。GA若接入，任何交叉、变异、2-opt输出都必须独立重算全部时序和约束。

### 5.2 原因与英文文案

| code | 判定证据 | 界面短句／下一步 |
| --- | --- | --- |
| NO_AVAILABLE_VEHICLE | 所有符合类型的设备不可用 | No eligible vehicle is available. / Review availability. |
| PAYLOAD_EXCEEDED | 剩余可用且符合类型车辆均不能承载；记录需求与容量 | Load exceeds available payload. / Change load or resources. |
| TIME_WINDOW_UNREACHABLE | 对指定快照、规则及被检查候选算出的到达均超限 | No checked assignment meets the arrival window. / Review window or resources.；不声称全局数学无解 |
| RETURN_BUDGET_EXCEEDED | 含完整返程的单趟时长超上限 | Trip exceeds the return budget. / Review route or vehicle. |
| SHIFT_LIMIT_EXCEEDED | 返仓时间超过班次结束 | Return would exceed the shift limit. / Review schedule. |
| NO_ROUTE | 缺已允许路段／不可达；不能靠示意直线补路线 | No allowed route is available. / Review travel data. |
| SEARCH_NO_ASSIGNMENT | 已检查的搜索没找到可分配项，没有充分具体不可行证据 | Search did not find an assignment. / Retry or revise inputs. |
| CALCULATION_ERROR | 规划器错误、输出结构错误或缺关键校核字段 | Calculation failed. / Retry planning.；结果不是可批准方案 |

可输出多个核查原因；主因按类型／可用性→载荷→路径→时间窗→返程预算→班次排序，不掩盖其他已知限制。未规划任务显示Not planned yet而不是Unassigned。已计算失败有明确code；不能把空原因列表视为成功。

## 6. 操作弹层与简洁英文文案

| 时机 | 标题／说明 | 动作 |
| --- | --- | --- |
| 完整方案批准 | Approve this simulation plan? / This approves the current assignments only. | Cancel / Approve plan |
| 部分方案批准 | Approve a partial plan? / 1 task will remain unassigned. | I acknowledge the unassigned task.；Cancel / Approve partial plan |
| 修改输入 | Update inputs? / The current plan and approval will become invalid. | Cancel / Save changes |
| 设备事件 | Mark UAV-01 unavailable? / The simulation will pause and require a new plan. | Cancel / Mark unavailable |
| 新方案待批准 | New plan requires approval. / Review the updated assignments before resuming. | Review new plan |
| 结束未完成模拟 | End with unfinished tasks? / Unassigned and interrupted tasks will be kept in the record. | Cancel / End simulation |

全局标签固定：Proposed extension；Illustrative data；Simulation only。计算结果标Calculated from demo-v1，在详情中可复查输入、计算链及快照。不要使用Optimised successfully、Live fleet、Guaranteed on-time等无证据文案。

## 7. 后续实现的验收场景（本轮未实施用户测试）

| ID | 触发／输入 | 必须出现的结果 |
| --- | --- | --- |
| A01 | T01–T03正常演示 | 各时间来自计算；Suggested不自动批准；批准后手动启动；服务结束及返仓后全完成 |
| A02 | 加入T04=25 kg | T04保持Unassigned＋容量证据，ETA为空；Partial批准要求承认未分配 |
| A03 | 启动前保存新窗口或载荷 | r增加，旧Suggested／Approved失效；旧Start被后端状态校验拒绝 |
| A04 | 异步计算返回前输入改变 | 丢弃过时活动结果；不得恢复旧Suggested或旧批准 |
| A05 | UAV-01不可用 | 暂停、旧批准失效、新方案Suggested；T01新分配若超窗则Unassigned，不强行保留原ETA |
| A06 | T02窗口缩至09:03–09:03 | 正常04到达不再满足；设备异常后只剩AGV时无法在03到达；重新计算并明确原因 |
| A07 | 全部设备不可用或全部任务超载 | 零Assigned；保留任务；不可批准，不显示成功；可结束为未完成记录 |
| A08 | 规划器错误／字段缺失 | Calculation failed；无可批准候选；原因不能伪装成时间窗不可行 |
| A09 | 普通暂停且输入未变 | 批准仍有效可恢复；异常暂停与普通暂停不混用 |
| A10 | 运行中事件、部分任务已完成 | Delivered历史不修改／重派；异常后剩余任务重新校核；检查点回滚提示明确 |
| A11 | 部分模拟结束 | Assigned tasks completed; N tasks remain unassigned；不能显示All tasks completed |
| A12 | ETA恰好等于窗端点 | 整数秒校核通过；显示格式舍入不能改变判定 |

本轮仅复算示例数学和检查SVG布局，没有运行原调度程序或开展用户测试。后续开发需要执行上述验收，不能提前将“必须出现”改为“已通过”。

## 8. SVG演示数据与独立复算

全部为本次新增Illustrative data，非FY01 s29默认值；没有性能提升比例。计算起点09:00（内部t=0秒），模拟班次结束09:45。

| 设备 | 可用性r1／r2 | 载荷kg | 速度m/s | 单趟上限min | 周转min |
| --- | --- | --- | --- | --- | --- |
| UAV-01 | Available／Unavailable | 2 | 5 | 10 | 2 |
| AGV-01 | Available／Available | 20 | 1 | 30 | 2 |

| 任务 | 工位 | kg | 到达窗 | 服务min | UAV往程m | AGV往程m |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | A | 1 | 09:01–09:05 | 1 | 600 | 360 |
| T02 | B | 10 | 09:03–09:07 | 2 | 240 | 240 |
| T03 | C | 8 | 09:10–09:20 | 2 | 360 | 360 |
| T04 | D | 25 | 09:00–09:30 | 2 | 300 | 300 |

两个类型均为eligible，载荷是实际筛选条件；不将“轻量必须UAV”写死。r1示例候选：T01→UAV-01 Trip1；T02→AGV-01 Trip1；T03→AGV-01 Trip2；T04未分配。候选安排是Illustrative data的预设候选，不宣称由GA优化；下列时序由独立计算生成。

| 输入／任务 | 出发 | travel秒 | ETA | 服务完成 | 返仓 | 单趟min | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| r1 T01 | 09:00 | 120 | 09:02 | 09:03 | 09:05 | 5 | Within window；1≤2 kg；5≤10 min |
| r1 T02 | 09:00 | 240 | 09:04 | 09:06 | 09:10 | 10 | Within window；10≤20 kg；10≤30 min |
| r1 T03 | 09:12 | 360 | 09:18 | 09:20 | 09:26 | 14 | Within window；8≤20 kg；14≤30 min |
| r1 T04 | — | — | — | — | — | — | PAYLOAD_EXCEEDED：25>2及20 kg |
| r2 T01候选检查 | 09:00 | 360 | 09:06（仅检查值） | 09:07 | 09:13 | 13 | 超过09:05；正式Unassigned，ETA为空 |
| r2 T02 | 09:00 | 240 | 09:04 | 09:06 | 09:10 | 10 | 新Suggested，仍需批准 |
| r2 T03 | 09:12 | 360 | 09:18 | 09:20 | 09:26 | 14 | 新Suggested，仍需批准 |
| r2 T04 | — | — | — | — | — | — | PAYLOAD_EXCEEDED：25>可用AGV的20 kg |

r2事件为09:00 UAV不可用，处理优先于同刻出发。T01即使让AGV最早出发也09:06到达，因此该演示检查不能满足09:05上限；这是给定demo-v1输入下的计算证据。r2仍可保留T02／T03为Partial。零可用设备的附加边界计算结果为四个任务Unassigned、Assigned=0、批准禁用。

三个图示时态保持区别：ui01为r1输入Ready；ui02为r1 P01 Suggested Partial；ui03为原P01已批准但09:00异常后Invalidated／Paused；ui04为r2 P02新Suggested Partial。这是界面状态示例序列，不是已经发生的用户操作记录。

## 9. 设计与个人贡献记录

本稿的布局、状态和计算规则为本次辅助提案。Peiming需要选择并解释spec02 R01–R09；目前均待确认，不能将本稿署为本人已独立完成或称为“经过多轮用户验证”。采访、测试、迭代及本人决策发生后另记日期、参与者和真实证据。第一作者及会议报告经历沿用spec01，不由本次SVG扩张为原代码归属。

