# 2026 新实现：启发式 → 任务排列 GA

方法版本two-stage-permutation-ga-2026-v1；物理模型沿用python-demo-2026-v2。paper01／fy01仅支持两阶段启发式加GA的概念；原源码、编码、种群传递和权重未取得。以下编码、解码、选择、交叉、变异、精英、停止条件和代价系数均是**2026新增实现及演示假设**，不是严格复现、近似最优或原研究指标验证。未实现2-opt。

## 1. 实际衔接

1. 第一阶段真正调用原有construct_plan(problem, mode, seed)，生成完整或明确部分计划。
2. 原构造顺序urgency_order=(latest, latest−earliest, earliest, task_id)产生种子染色体，每个任务ID恰好一次，包括第一阶段未分配任务。
3. 解码种子时使用相同mode和固定decoder_seed，必须与第一阶段Plan逐字段相等；失败直接报内部错误。不是仅把第一阶段结果写进报告，而种群实际没有用它。
4. 初始种群index=0就是这一重新解码的个体；默认24个个体中其余11个由种子做1–3次交换／插入扰动、12个随机排列。小种群可能比例不同；允许重复个体，避免任务少时反复去重造成死循环。
5. initial-population.json保留来源、染色体、独立校核后的目标。run.json的heuristic_seed保留位置0、原顺序及decoded_plan_matches_initial证明。

## 2. 编码与确定性解码

染色体是全部任务ID的排列，其含义是**依次考虑任务的优先顺序**，不是最终设备路线的直接编码。设备、分趟和时刻由解码器决定。

decode_chromosome将排列传给construct_plan的task_order；不再按deadline重新排序。每个基因依序处理，对设备当前最后一趟的所有插入位置和返仓周转后的新趟测试；每个候选重算全路线、整趟装载、全部站点等待／装卸／服务、返程、单趟续航及可用时间。接受候选的本地排序沿用已有启发式：新增任务加权迟到、旅行秒、服务开始、是否新趟，再用固定decoder_seed平局。

最终站点顺序可与染色体顺序不同，因为允许插入；但染色体实际改变构造先后，进而改变设备选择、行程和覆盖。在单车容量2 kg且可用时间只能容纳一趟的单元测试中，T1→T2与T2→T1分别安排不同任务，验证没有忽略染色体。

所有代数和同一染色体都使用同一个decoder_seed；GA进化RNG与解码RNG分开。固定输入／mode／参数／seed产生相同结果。缓存只复用同一次运行内已独立校核的相同染色体，不缓存不同输入或参数。

不能安排的基因放进unassigned并记录候选失败；不删除基因、不拆任务、不通过超载或hard迟到使数量变小。基因全部考虑后结束，不无限重试。

## 3. 物理约束和独立校核

check_trip过滤所有物理不合格候选；decode后check_plan重新计算。同趟／跨趟任务唯一、完整归属、assigned与unassigned互斥、同设备跨趟时间链、完整载荷、适配、可用性、旅行边、返程续航和仓库时间均校核。hard只接受服务开始窗无违约，soft保留迟到；soft仍不放松物理约束。

每个新个体都通过check_plan才能计算适应度，非法计划直接拒绝参与比较；输出第一阶段和最优GA方案之前又重新校核，不信任缓存的ETA或valid。独立校核不调用启发式或GA。没有设备实际执行或Delivered声明。

## 4. 声明的目标、系数及单位

对校核有效的计划P：

```text
U(P) = len(unassigned)
transport_cost(P) = Σ_trip alpha_vehicle_type * travel_s_trip
lateness_penalty(P) = beta * Σ_assigned_task lambda_i * lateness_s_i
C(P) = transport_cost(P) + lateness_penalty(P)
fitness(P) = (U(P), C(P))      # 严格字典序最小化
```

| 参数 | 默认 | 单位 | 2026新增含义 |
| --- | --- | --- | --- |
| UAV运输alpha | 0.02 | penalty_unit/s | 所有UAV旅行秒，含返仓 |
| AGV运输alpha | 0.01 | penalty_unit/s | 所有AGV旅行秒，含返仓 |
| 任务lambda_i | 输入lateness_cost_per_s；v1省略为1 | penalty_unit/s | 此前显式的演示迟到系数；固定8任务算例取1／2／4 |
| 全局beta | 1.0 | 无量纲 | 缩放全部任务迟到罚值 |
| 合计C | 计算值 | penalty_unit | 运输与迟到同一演示罚值单位 |
| 未分配U | 计算值 | count | 优先于任何代价差额，不能靠放弃任务取得优势 |

这些系数不代表实测经济成本、货币、能耗或原研究权重。运输只计旅行，工位等待／服务和仓库装卸／周转的经济系数在本版假设为0；这些过程仍完整参与时间及物理约束。没有运输固定启动费或未分配标量罚系数。

内部目标用Fraction作精确字典序比较；导出用有限JSON数值。指标summary.lateness_cost是原任务权重罚值，objective.lateness_penalty另外乘beta。两阶段都用上述同一目标评估比较，但第一阶段的本地贪心排序不声称等价于全局目标最小化。

U较小时即使C大也更好；只有U相等才比较C。相同目标不替换最优档案，尤其没有严格改善时保留第一阶段原计划。可减少未分配时才允许优先接受更高代价，不能反过来为了低代价增加未分配。

## 5. GA算子与停止

| 项目 | 已实现规则 |
| --- | --- |
| 选择 | size=3的锦标赛，每次从当前种群抽样，按(U,C)取最好 |
| 交叉 | OX：复制第一父代片段，按第二父代循环顺序填剩余位置；保留任务排列，无遗漏／重复 |
| 变异 | 等概率交换两基因或移出一个基因插入另一位置 |
| 精英 | 默认2：显式best-known档案成员＋排名最好的其他精英位置；允许重复，人口规模固定 |
| 档案 | 初始化为第一阶段；初始种群和每代只有严格更好才更新；最终不得劣于第一阶段 |
| 停止 | 最大40代；连续12代无严格档案改善停止；patience=0禁用停滞停止 |
| 边界 | 少于2个基因直接记录代0并结束；generations=0不繁殖，但仍评估初始种群 |
| 2-opt | **未实现**；当前行程插入不等同于2-opt |

默认population=24、crossover=0.9、mutation=0.25、elite=2、tournament=3、seed=2026。所有参数可CLI显式改变，计数／概率／系数严格校验。seed既记录进化种子，也记录独立固定解码种子，两个RNG对象互不消耗对方的状态。

代0指已评估的初始种群，不是第一阶段本身。每代记录当代最优、累计最优、染色体、种群不同排列数、累计独立解码数、缓存命中数和连续停滞代数。best_found_generation=0表示较好方案已在初始种群找到，不归因于之后的交叉／变异代数。停止不证明收敛到全局最优。

## 6. CLI与导出

```powershell
.\Run-OnTime-Python.cmd optimize data/cases/normal.json --mode soft --seed 2026 --population-size 24 --generations 40 --elite-count 2 --tournament-size 3 --crossover-rate 0.9 --mutation-rate 0.25 --patience 12 --uav-transport-per-s 0.02 --agv-transport-per-s 0.01 --lateness-multiplier 1 --output-dir outputs/ga/normal-soft
.\Run-OnTime-Python.cmd evaluate outputs/ga/normal-soft/input-snapshot.json outputs/ga/normal-soft/initial/plan.json --output outputs/ga/normal-soft/initial/checked.json
.\Run-OnTime-Python.cmd evaluate outputs/ga/normal-soft/input-snapshot.json outputs/ga/normal-soft/ga/plan.json --output outputs/ga/normal-soft/ga/checked.json
```

有系统Python时可用python run_ontime.py。两阶段命令optimize独立于原schedule入口；schedule仍只运行第一阶段，以保留其已验证行为。

```text
outputs/ga/<case>-<mode>/
  input-snapshot.json      规范化输入（含v1声明默认），SHA256在run.json
  parameters.json          GA、固定解码种子及成本参数；two_opt_implemented=false
  initial-population.json  所有初始染色体、来源、目标、校核记录
  initial/                 第一阶段plan.json、plan-input.json及6张CSV
  ga/                      最优已知GA计划及同样CSV
  comparison.json/.csv     覆盖、行程、旅行、等待、迟到和运输／迟到／合计代价比较
  task-comparison.csv      同一任务两阶段状态、设备、行程、时间及原因
  iterations.json/.csv     从代0起每代当代及累计最优目标
  run.json                 完整结果、种子往返证明、停止理由、改善标记和输入哈希
```

独立evaluate输出只重算物理计划；GA总代价由目标模块从重新校核后的时间计算。comparison的delta是GA−初始，覆盖／代价必须联合解释；任务未分配时CSV时间留空，不虚构ETA。迭代记录不是算法性能普遍证据。

## 7. 本次实际运行

详见README及outputs/ga/run-record.json。同一已保存的8任务数据，各模式分别运行两阶段；输入、种子、全部参数都保留。正常算例运输及总代价12.26→12.16，覆盖仍8/8，旅行1135→1130 s。这一较好方案在初始种群（代0）找到，随后12代无进一步改善，按patience停止。

hard时间窗冲突和设备不可用两种模式没有严格改善，输出保留第一阶段原计划；soft时间窗冲突仍有34 s迟到、34 penalty_unit迟到罚值，只有本次运输代价改变。不得写成普遍提升、近似最优或原研究指标得到验证。
