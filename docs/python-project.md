# 2026 Python 调度核心 v2

依据实际读取材料重新实现，2025研究源码未找到。全部运行依赖为Python标准库（3.10+）；现已接入2026新增排列GA两阶段方法，仍未实现2-opt、真实避障或设备部署。模型及来源见[model.md](model.md)，输入结构见[input.schema.json](input.schema.json)，演示参数见[scenarios.md](scenarios.md)，GA衔接及规则见[two-stage.md](two-stage.md)。

## 运行命令

两阶段入口（保留下面的schedule作为第一阶段独立入口）：

```powershell
.\Run-OnTime-Python.cmd optimize data/cases/normal.json --mode soft --seed 2026 --output-dir outputs/ga/normal-soft
```

完整GA参数、成本系数、代数／停止控制和导出说明见[two-stage.md](two-stage.md)。输出含initial、ga两个计划目录，comparison及逐任务比较，initial-population和iterations记录；每个最终计划已重新独立校核。

在项目根目录使用系统Python：

```powershell
python run_ontime.py generate --seed 2026 --output-dir data/cases
python run_ontime.py validate data/cases/normal.json
python run_ontime.py schedule data/cases/normal.json --mode soft --seed 2026 --output-dir outputs/cases/normal-soft
python run_ontime.py schedule data/cases/window_conflict.json --mode hard --seed 2026 --output-dir outputs/cases/window_conflict-hard
python run_ontime.py evaluate data/cases/normal.json outputs/cases/normal-soft/plan.json --output outputs/cases/normal-soft/checked.json
python -m unittest discover -s tests -p "test_*.py" -v
```

本机Python未在PATH；Windows入口使用当前用户的Codex随附Python，否则调用系统python。本机可以直接运行：

```powershell
.\Run-OnTime-Python.cmd generate --seed 2026 --output-dir data/cases
.\Run-OnTime-Python.cmd validate data/cases/normal.json
.\Run-OnTime-Python.cmd schedule data/cases/normal.json --mode soft --seed 2026 --output-dir outputs/cases/normal-soft
.\Run-OnTime-Python.cmd evaluate data/cases/normal.json outputs/cases/normal-soft/plan.json --output outputs/cases/normal-soft/checked.json
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s tests -p "test_*.py" -v
```

也可设置PYTHONPATH=src再运行python -m ontime。无须pip安装，不用启动Node服务。

- generate的--seed默认2026，控制输入数据生成；--output-dir默认data/cases。
- schedule的--seed默认0，仅控制实质评分平局；无模式参数时使用输入window_mode，输入省略时为soft。
- --output-dir写JSON和CSV；--output保留单JSON旧入口，两者互斥；不指定输出则打印JSON。
- evaluate重新计算简洁路线；导出plan.json默认继承其mode和seed，--mode可覆盖。其seed只是运行记录，不参与校核。
- 退出码0表示格式有效／所排路线约束有效，**部分方案也可能为0**；检查complete和unassigned确认覆盖。退出码2表示输入／文件错误或计划违反硬约束。

## 数据结构与模块

| 记录／函数 | 职责 |
| --- | --- |
| Task | 重量、工位、服务开始窗、卸货、服务、适配、迟到权重 |
| Vehicle | 容量、速度、可用时段、单趟时限、装卸、周转及available |
| Trip | 设备、任务序列、装货开始；起终点仓库由计算器明确闭合 |
| ScheduledStop | 到达、等待、卸货／服务、完成、迟到及代价、剩余载荷 |
| Plan | 行程、明确未分配任务及原因、mode、seed |
| Evaluation／TripEvaluation | 重算时间账目、校核证据、valid／complete／覆盖汇总 |
| Problem | 输入快照的显式模型、两套矩阵与单位 |
| input.load_instance | 严格加载为Problem；load_problem保留旧字典入口 |
| scheduler.construct_plan | 返回Plan；按紧迫程度、完整可行性和加权迟到代价插入当前行程 |
| scheduler.construct_plan(task_order=...) | 显式排列驱动解码，不重做紧迫排序 |
| ga.run_two_stage | 真正运行第一阶段、验证种子重解码、进化并保存最优已知方案 |
| evaluate.check_plan | 返回Evaluation，不调用启发式、不信任预存ETA；独立重算 |
| export.export_results | JSON、CSV明细及汇总 |
| generate.synthetic_cases | 固定种子正常及三个异常算例 |

Task／Vehicle／Trip／Plan等输入记录为frozen dataclass；Problem内矩阵是嵌套字典，不声称完全不可变。schedule／evaluate_plan保留字典适配输出。

## 输入JSON合同

顶层要求schema_version、scenario_label、depot_id、stations、vehicles、tasks、travel_time_s。schema v2另外要求：

- units必须精确为{"mass":"kg","distance":"m","time":"s","speed":"m/s","cost":"penalty_unit"}，不做隐式转换。
- 每设备有speed_m_s > 0，每任务有lateness_cost_per_s >= 0；罚值是2026演示单位，不是钱或原研究参数。
- 全部时间是非负整数秒，trip_limit_s > 0；需求／容量是有限正kg；布尔值不作数值接受。
- 旅行矩阵完整包含所有节点及UAV／AGV两套，允许非对称；对角0，其他非负整数秒或null（不可通行）。
- 距离矩阵可选，单位m；若有须结构完整，允许null表示未知距离。没有距离不输出假0。
- 适配取eligible_types与可选eligible_vehicle_ids交集。超载／无设备是合法输入，由调度保留unassigned；负数、NaN、重复键／ID、未知字段、缺矩阵节点和逆序窗口是输入错误。
- metadata只用于来源描述，不改变规则。核心旅行时间只来自travel_time_s；speed_m_s不会偷偷重算时间。需要设备专属矩阵时应另扩展模型。
- v1旧输入仍可运行，缺失速度为None、缺失权重按本项目新增默认1 penalty_unit/s，不猜原研究值。v1的kg/m/s含义由字段名和文档声明；新算例使用v2显式单位。
- 空任务／空设备允许；stations至少一个。JSON Schema供外部编辑器使用，运行时用标准库执行字段、单位和跨字段校验。

## 独立校核手写计划

可用以下简洁JSON，装货开始不是离仓时刻：

```json
{
  "trips": [
    {"trip_id":"manual-1","vehicle_id":"UAV-01","task_ids":["T01"],"load_start_s":0}
  ]
}
```

仅trips格式会显式将其他任务列为not_in_plan；新导出plan-input.json带完整unassigned。若显式给unassigned但遗漏某任务、或同时列为assigned／unassigned、或重复任务，校核失败。同设备数组顺序是执行顺序，跨车不要求全局排序；同车下一趟必须在上趟返仓卸货和周转之后。

## JSON／CSV输出

| 文件 | 内容 |
| --- | --- |
| plan.json | 全部候选、规则、mode／seed、汇总、约束证据和原因 |
| plan-input.json | 可重新校核的路线与完整unassigned |
| trips.csv | 整趟载荷、路线、速度、装货、返回、续航、装卸、周转及代价 |
| stops.csv | 任务重量、时间窗、到达、等待、服务、迟到及代价；每任务一行 |
| legs.csv | 各有向矩阵边、旅行时间及可选距离，含返仓边 |
| unassigned.csv | 明确主因、全部失败类型及候选证据JSON；无编造ETA |
| checks.csv | 计划／行程全部通过或失败检查及证据 |
| summary.csv | 覆盖、valid／complete、行程数、旅行／等待／迟到秒和罚值 |

CSV为UTF-8 BOM；空表仍写表头；所有时间列s、距离m、载荷kg。stop.status=planned，execution_status=candidate_only；不代表送达或真实设备执行。next_ready_s展示周转后时刻；turnaround_applied仅有下一趟时为true，末趟planned_end_s是仓库卸货结束。

迟到代价=sum(max(0, service_start_s−latest_s)×lateness_cost_per_s)。候选按新增迟到代价、新增旅行秒、任务服务开始、新趟标志排序；完全平局才使用seed。无可行候选即记录原因、进入下一任务，不会通过违规分配减少未分配。原因包括payload_exceeded、time_window_conflict、device_unavailable、no_compatible_vehicle、endurance_exceeded、availability_exceeded、route_unavailable以及no_feasible_candidate_found，附候选校核证据。

构造器只尝试当前最后行程插入及新趟，保留旧任务相对次序，不搜索其他行程／换车／延迟离仓；GA通过改变任务考虑顺序搜索构造器可产生的其他计划。search_exhaustive=false，无候选不是全局无解证明。新成本系数不代表原权重，不宣称最优或复现2025 GA。第一阶段结果见outputs/cases/run-record.json，两阶段见outputs/ga/run-record.json；不作为性能评测。
