"""Execute functional checks, preserve actual statuses and generate docs/validation.md."""
import argparse
from datetime import datetime
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from ontime.export import export_two_stage, write_json
from ontime.ga import GAParameters, run_two_stage
from ontime.generate import synthetic_cases
from ontime.input import as_problem


REQUESTED = [
 ('单任务正常配送','test_replan.ExplicitBoundaryTests.test_single_task_normal_delivery'),
 ('整趟累计载荷超过容量','test_ontime.TimingTests.test_whole_trip_load_not_each_task'),
 ('去程可行但返仓超续航','test_ontime.TimingTests.test_return_is_required_by_endurance'),
 ('提前到达等待','test_replan.ExplicitBoundaryTests.test_early_wait_is_feasible_and_counted'),
 ('等待计入续航','test_ontime.TimingTests.test_waiting_counts_toward_endurance'),
 ('hard 不满足 / soft 迟到','test_ontime.TimingTests.test_soft_default_and_hard_lateness'),
 ('多趟与仓库周转','test_ontime.TimingTests.test_multitrip_turnaround_not_final_shift_requirement'),
 ('同一设备行程不能重叠','test_ontime.PlanTests.test_overlap_rejected'),
 ('设备不可用 / 适配为硬约束','test_ontime.TimingTests.test_unavailable_or_ineligible_is_hard_in_soft'),
 ('空任务集 / 无设备终止','test_ontime.PlanTests.test_empty_tasks_and_no_devices_terminate'),
 ('非法字段、单位、数值','test_ontime.InputTests.test_bad_units_unknown_fields_and_numeric_values'),
 ('全部任务不可分配','test_replan.ExplicitBoundaryTests.test_all_tasks_unassignable_are_retained'),
 ('跨行程重复任务拒绝','test_ontime.PlanTests.test_duplicate_task_across_trips_rejected'),
 ('无静默丢弃 / 不重复分类','test_core_v2.TypedPlanTests.test_explicit_coverage_cannot_drop_or_double_classify_task'),
 ('启发式固定种子复现','test_core_v2.InsertionTests.test_seed_reproducible_and_used_only_for_ties'),
 ('GA 全运行固定种子复现','test_ga.EvolutionTests.test_archive_history_reproducible_and_all_constraint_modes'),
 ('校验接口禁止伪造设备容量','test_replan.ExplicitBoundaryTests.test_dictionary_adapter_cannot_override_device_capacity'),
 ('重规划固定已完成与已装载任务','test_replan.ReplanningTests.test_completed_and_active_loaded_tasks_are_frozen'),
 ('重规划禁止自动批准且可复现','test_replan.ReplanningTests.test_unapproved_and_fixed_seed_reproducible'),
 ('在途故障明确拒绝','test_replan.ReplanningTests.test_active_failed_device_is_explicitly_rejected'),
 ('篡改历史 / 故障后新行程拒绝','test_replan.ReplanningTests.test_tampered_frozen_or_new_failed_vehicle_is_rejected'),
 ('重规划 CLI 成功与拒绝出口','test_replan_cli.CheckpointCLITests.test_cli_replan_exports_unapproved_candidate_and_rejects_active_failure'),
 ('重规划非法计划 JSON 干净拒绝','test_replan_cli.CheckpointCLITests.test_malformed_plan_json_has_clean_input_error_exit'),
]


class RecordedResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.records={}
    def startTest(self,test):
        self.records[test.id()]={'test':test.id(),'status':'未执行'}
        super().startTest(test)
    def addSuccess(self,test):
        self.records[test.id()]['status']='已通过';super().addSuccess(test)
    def addFailure(self,test,err):
        self.records[test.id()].update(status='失败',detail=self._exc_info_to_string(err,test))
        super().addFailure(test,err)
    def addError(self,test,err):
        self.records[test.id()].update(status='失败',detail=self._exc_info_to_string(err,test))
        super().addError(test,err)
    def addSkip(self,test,reason):
        self.records[test.id()].update(status='未执行',detail=reason);super().addSkip(test,reason)
    def addSubTest(self,test,subtest,err):
        if err:
            self.records[test.id()].update(status='失败',detail=self._exc_info_to_string(err,test))
        super().addSubTest(test,subtest,err)


def main(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py')
    result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=RecordedResult).run(suite)
    (output/'unittest.log').write_text(stream.getvalue(),encoding='utf-8')
    cases=[]
    for name,data in synthetic_cases(2026).items():
        for mode in ('hard','soft'):
            directory=output/'cases'/f'{name}-{mode}'
            problem=as_problem(data)
            run=run_two_stage(problem,mode,GAParameters(seed=2026))
            export_two_stage(run,directory)
            cli=[]
            for phase in ('initial','ga'):
                command=[sys.executable,str(ROOT/'run_ontime.py'),'evaluate',str(directory/'input-snapshot.json'),
                         str(directory/phase/'plan.json'),'--output',str(directory/phase/'checked.json')]
                check=subprocess.run(command,capture_output=True,text=True)
                cli.append({'phase':phase,'exit_code':check.returncode,'stdout':check.stdout,'stderr':check.stderr})
            cases.append({'case':name,'mode':mode,'status':'已通过' if all(c['exit_code']==0 for c in cli) else '失败',
                          'initial':run['initial']['objective'],'ga':run['ga']['objective'],
                          'unassigned':run['ga']['unassigned_task_ids'],'checks':cli})
    records=list(result.records.values())
    counts={status:sum(r['status']==status for r in records) for status in ('已通过','失败','未执行')}
    saved={'executed_at':datetime.now().astimezone().isoformat(),'python':platform.python_version(),
           'functional_tests_only':True,'counts':counts,'tests':records,'case_runs':cases,
           'not_executed':['真实 UAV/AGV 与硬件遥测','在途故障救援 / 改道 / 抛载','真实障碍物规避与充电曲线',
                           '真实工厂地图 / 经济成本测量','2025 源码复现 / 原研究指标验证',
                           '用户可用性测试 / 操作员批准流程 / 生产部署','2-opt（未实现）'],
           'history':json.loads((ROOT/'docs/validation-history.json').read_text(encoding='utf-8'))}
    write_json(output/'validation-results.json',saved)
    statuses={r['test']:r['status'] for r in records}
    lines=['# Python 功能验证记录','',f"实际执行时间：{saved['executed_at']}；Python {saved['python']}；输入均为 Illustrative data。",
           '',f"最终功能测试：已通过 {counts['已通过']}；失败 {counts['失败']}；未执行 / skip {counts['未执行']}。",
           '八组正常 / 异常算例 × hard / soft 已重新运行启发式 + GA，16 份最终计划另由 CLI evaluate 从保存的输入重算。',
           '预期的超载、时间窗、不可用和重复任务被拒绝，属于负向测试通过；有效的部分计划不表示所有任务可配送。',
           '', '## 用户要求的检查','', '| 检查 | 最终状态 | 实际测试 |','| --- | --- | --- |']
    lines.extend(f'| {label} | {statuses.get(test,"未执行")} | `{test}` |' for label,test in REQUESTED)
    lines+=['','## 首轮失败、修复及重跑','',
            '1. 旧 evaluate_trip 字典适配接口可使用调用者伪造的设备容量。新增回归测试先实际失败（未抛出 InputError），修复为必须与已校验输入设备一致，再重跑该测试和完整测试集。此问题影响单趟字典接口；check_plan 本来就从 Problem 查设备。',
            '2. 新增重规划测试把 U2 下次可装载时间误写为 130 s。正确账目为 30 + 10 + 20 + 5 + 25 + 10 + 20 = 120 s；修正测试期望后重跑受影响的新增测试，再执行完整回归。调度时间计算未因此改变。',
            '3. 曾把 unittest 参数传给调度 CLI 包装器，命令被拒绝。改用 Python -m unittest；新增 Run-Validation.cmd 是正确的一键验证入口。',
            '4. 新增 replan CLI 在计划 JSON 为数组 [] 时抛出 AttributeError、显示 traceback 并退出 1。回归测试实际复现后，修复为读取字段前校验 JSON 根必须为对象，返回明确 InputError 和退出码 2；重跑 CLI 两项及完整测试集。',
            '5. 冻结但尚未开始的片段虽 executed_s=0，原 executed_until_s 却写入未来开始时刻。新增断言实际失败后，修复为未开始片段的 executed_until_s=null，所有已有执行截止时刻不晚于检查点。重跑检查点测试及完整回归；物理路线与任务分区不变。',
            '', '失败历史保存在 [validation-history.json](validation-history.json)。最终未修复失败数见上方实际统计。',
            '', '## 正常及异常实际运行','', '| 算例 | 模式 | 状态 | 初始 / GA 未分配 | 初始 / GA 总罚值 | GA 未分配 ID |',
            '| --- | --- | --- | --- | --- | --- |']
    for c in cases:
        lines.append(f"| {c['case']} | {c['mode']} | {c['status']} | {c['initial']['unassigned_count']} / {c['ga']['unassigned_count']} | {c['initial']['total_cost']:g} / {c['ga']['total_cost']:g} | {', '.join(c['unassigned']) or '无'} |")
    lines+=['','成本单位 penalty_unit，运输系数 UAV 0.02 / AGV 0.01 penalty_unit/s，迟到倍率 1；仅为演示假设。',
            '', '## 未执行的检查','']
    lines.extend('- 未执行：'+label+'。' for label in saved['not_executed'])
    lines+=['','这些是功能与约束测试，**不是用户可用性测试**。未开展操作员访谈、任务完成率测试或真实配送试验。',
            '', '## 可复现命令与证据','', '```powershell', '.\\Run-Validation.cmd', '.\\Build-Portfolio.cmd --seed 2026 --output-dir outputs/portfolio', '```','',
            '有系统 Python 时：`python scripts/run_validation.py`、`python scripts/build_portfolio.py --seed 2026 --output-dir outputs/portfolio`。',
            '', '原始状态 / 断言日志：`outputs/validation/validation-results.json` 与 `unittest.log`；逐计划独立校验保存在 `outputs/validation/cases/*/{initial,ga}/checked.json`。',
            '作品集记录与限制见 [portfolio.md](portfolio.md)；重规划规则见 [replanning.md](replanning.md)。固定种子复现检查比较完整搜索记录，不把 PNG 跨平台逐像素相等当作算法复现。']
    (ROOT/'docs/validation.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'counts':counts,'case_runs':len(cases),'all_case_checks_passed':all(c['status']=='已通过' for c in cases)},ensure_ascii=False))
    return 0 if result.wasSuccessful() and all(c['status']=='已通过' for c in cases) else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'outputs/validation')
    raise SystemExit(main(parser.parse_args().output_dir))
