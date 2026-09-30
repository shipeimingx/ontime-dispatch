# Python 功能验证记录

实际执行时间：2026-09-30T19:34:31.732103+08:00；Python 3.12.14；输入均为 Illustrative data。

最终功能测试：已通过 66；失败 0；未执行 / skip 0。
八组正常 / 异常算例 × hard / soft 已重新运行启发式 + GA，16 份最终计划另由 CLI evaluate 从保存的输入重算。
预期的超载、时间窗、不可用和重复任务被拒绝，属于负向测试通过；有效的部分计划不表示所有任务可配送。

## 用户要求的检查

| 检查 | 最终状态 | 实际测试 |
| --- | --- | --- |
| 单任务正常配送 | 已通过 | `test_replan.ExplicitBoundaryTests.test_single_task_normal_delivery` |
| 整趟累计载荷超过容量 | 已通过 | `test_ontime.TimingTests.test_whole_trip_load_not_each_task` |
| 去程可行但返仓超续航 | 已通过 | `test_ontime.TimingTests.test_return_is_required_by_endurance` |
| 提前到达等待 | 已通过 | `test_replan.ExplicitBoundaryTests.test_early_wait_is_feasible_and_counted` |
| 等待计入续航 | 已通过 | `test_ontime.TimingTests.test_waiting_counts_toward_endurance` |
| hard 不满足 / soft 迟到 | 已通过 | `test_ontime.TimingTests.test_soft_default_and_hard_lateness` |
| 多趟与仓库周转 | 已通过 | `test_ontime.TimingTests.test_multitrip_turnaround_not_final_shift_requirement` |
| 同一设备行程不能重叠 | 已通过 | `test_ontime.PlanTests.test_overlap_rejected` |
| 设备不可用 / 适配为硬约束 | 已通过 | `test_ontime.TimingTests.test_unavailable_or_ineligible_is_hard_in_soft` |
| 空任务集 / 无设备终止 | 已通过 | `test_ontime.PlanTests.test_empty_tasks_and_no_devices_terminate` |
| 非法字段、单位、数值 | 已通过 | `test_ontime.InputTests.test_bad_units_unknown_fields_and_numeric_values` |
| 全部任务不可分配 | 已通过 | `test_replan.ExplicitBoundaryTests.test_all_tasks_unassignable_are_retained` |
| 跨行程重复任务拒绝 | 已通过 | `test_ontime.PlanTests.test_duplicate_task_across_trips_rejected` |
| 无静默丢弃 / 不重复分类 | 已通过 | `test_core_v2.TypedPlanTests.test_explicit_coverage_cannot_drop_or_double_classify_task` |
| 启发式固定种子复现 | 已通过 | `test_core_v2.InsertionTests.test_seed_reproducible_and_used_only_for_ties` |
| GA 全运行固定种子复现 | 已通过 | `test_ga.EvolutionTests.test_archive_history_reproducible_and_all_constraint_modes` |
| 校验接口禁止伪造设备容量 | 已通过 | `test_replan.ExplicitBoundaryTests.test_dictionary_adapter_cannot_override_device_capacity` |
| 重规划固定已完成与已装载任务 | 已通过 | `test_replan.ReplanningTests.test_completed_and_active_loaded_tasks_are_frozen` |
| 重规划禁止自动批准且可复现 | 已通过 | `test_replan.ReplanningTests.test_unapproved_and_fixed_seed_reproducible` |
| 在途故障明确拒绝 | 已通过 | `test_replan.ReplanningTests.test_active_failed_device_is_explicitly_rejected` |
| 篡改历史 / 故障后新行程拒绝 | 已通过 | `test_replan.ReplanningTests.test_tampered_frozen_or_new_failed_vehicle_is_rejected` |
| 重规划 CLI 成功与拒绝出口 | 已通过 | `test_replan_cli.CheckpointCLITests.test_cli_replan_exports_unapproved_candidate_and_rejects_active_failure` |
| 重规划非法计划 JSON 干净拒绝 | 已通过 | `test_replan_cli.CheckpointCLITests.test_malformed_plan_json_has_clean_input_error_exit` |

## 首轮失败、修复及重跑

1. 旧 evaluate_trip 字典适配接口可使用调用者伪造的设备容量。新增回归测试先实际失败（未抛出 InputError），修复为必须与已校验输入设备一致，再重跑该测试和完整测试集。此问题影响单趟字典接口；check_plan 本来就从 Problem 查设备。
2. 新增重规划测试把 U2 下次可装载时间误写为 130 s。正确账目为 30 + 10 + 20 + 5 + 25 + 10 + 20 = 120 s；修正测试期望后重跑受影响的新增测试，再执行完整回归。调度时间计算未因此改变。
3. 曾把 unittest 参数传给调度 CLI 包装器，命令被拒绝。改用 Python -m unittest；新增 Run-Validation.cmd 是正确的一键验证入口。
4. 新增 replan CLI 在计划 JSON 为数组 [] 时抛出 AttributeError、显示 traceback 并退出 1。回归测试实际复现后，修复为读取字段前校验 JSON 根必须为对象，返回明确 InputError 和退出码 2；重跑 CLI 两项及完整测试集。
5. 冻结但尚未开始的片段虽 executed_s=0，原 executed_until_s 却写入未来开始时刻。新增断言实际失败后，修复为未开始片段的 executed_until_s=null，所有已有执行截止时刻不晚于检查点。重跑检查点测试及完整回归；物理路线与任务分区不变。

失败历史保存在 [validation-history.json](validation-history.json)。最终未修复失败数见上方实际统计。

## 正常及异常实际运行

| 算例 | 模式 | 状态 | 初始 / GA 未分配 | 初始 / GA 总罚值 | GA 未分配 ID |
| --- | --- | --- | --- | --- | --- |
| normal | hard | 已通过 | 0 / 0 | 12.26 / 12.16 | 无 |
| normal | soft | 已通过 | 0 / 0 | 12.26 / 12.16 | 无 |
| overload | hard | 已通过 | 1 / 1 | 12.26 / 12.16 | T08 |
| overload | soft | 已通过 | 1 / 1 | 12.26 / 12.16 | T08 |
| window_conflict | hard | 已通过 | 1 / 1 | 12.12 / 12.12 | T01 |
| window_conflict | soft | 已通过 | 0 / 0 | 46.26 / 46.16 | 无 |
| unavailable | hard | 已通过 | 4 / 4 | 10.44 / 10.44 | T01, T03, T05, T07 |
| unavailable | soft | 已通过 | 4 / 4 | 10.44 / 10.44 | T01, T03, T05, T07 |

成本单位 penalty_unit，运输系数 UAV 0.02 / AGV 0.01 penalty_unit/s，迟到倍率 1；仅为演示假设。

## 未执行的检查

- 未执行：真实 UAV/AGV 与硬件遥测。
- 未执行：在途故障救援 / 改道 / 抛载。
- 未执行：真实障碍物规避与充电曲线。
- 未执行：真实工厂地图 / 经济成本测量。
- 未执行：2025 源码复现 / 原研究指标验证。
- 未执行：用户可用性测试 / 操作员批准流程 / 生产部署。
- 未执行：2-opt（未实现）。

这些是功能与约束测试，**不是用户可用性测试**。未开展操作员访谈、任务完成率测试或真实配送试验。

## 可复现命令与证据

```powershell
.\Run-Validation.cmd
.\Build-Portfolio.cmd --seed 2026 --output-dir outputs/portfolio
```

有系统 Python 时：`python scripts/run_validation.py`、`python scripts/build_portfolio.py --seed 2026 --output-dir outputs/portfolio`。

原始状态 / 断言日志：`outputs/validation/validation-results.json` 与 `unittest.log`；逐计划独立校验保存在 `outputs/validation/cases/*/{initial,ga}/checked.json`。
作品集记录与限制见 [portfolio.md](portfolio.md)；重规划规则见 [replanning.md](replanning.md)。固定种子复现检查比较完整搜索记录，不把 PNG 跨平台逐像素相等当作算法复现。
