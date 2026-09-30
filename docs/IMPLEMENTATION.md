# 研究材料核查与原型实现记录

核查与实现日期：2026-09-30（北京时间）。第三项目：OnTime Dispatch / Coordinating Time-Critical Material Delivery: A UAV–AGV Service Concept。

## 已读取材料

目标目录：[02-Drafts](https://drive.google.com/drive/u/0/folders/15A1zlC9Dad2aluSUhPc94Y7wUuLM2xPQ)。目录列出 41 个直接子文件，没有子目录。完整元数据保存在 `sources/folder-manifest.json`。

核心规格已完整读取并在本地保留：

| 材料 | 阅读所得与实现依据 |
| --- | --- |
| [spec01 研究与代码核查](https://drive.google.com/file/d/1DUHDFi5RRJ8LP-RYj5FwBEsETajXDd0j/view) | S01–S08 支持仓库到工位、异构车辆、多行程、载荷／续航／窗口。C01–C05 和 K01–K12 明确原模型与源码未核实；不能把摘要或流程图当作代码。 |
| [spec02 调度服务设计](https://drive.google.com/file/d/1HlVTxu5oX47YI62i_UOptXGK43u7lskl/view) | D01–D12：输入→候选→批准→启动；未分配可见；版本失效；异常全局暂停；已完成事实保留；前台责任与模拟后台分离。 |
| [spec03 界面与交互规格](https://drive.google.com/file/d/1DevOfRvZyJ2eKwMdZQZxKvdXkg_2PHg6/view) | §2 三维生命周期、§3 四页、§4 数据契约、§5 demo-v1 计算、§7 A01–A12、§8 精确演示数据。 |
| ui01–ui04 SVG | 从实际 Drive 同步目录读取并复制留存。采用 #FAFAF7 / #182936 / #3463A7 和蓝灰信息层级；网页采用自适应侧边导航。 |
| ui06 设计包 | 已查看 ZIP 文件目录：spec02、spec03、四页 SVG、ui05 预览；没有研究源码。 |
| [paper01 UAVAGV Conference Abstract](https://drive.google.com/file/d/1Hgax_0xjf6frujkwxfjy2Kne6XLByMg0/view) | 直接读取摘要：MTCVRP-TW、运输成本＋时间违约罚项、分类/贪心＋GA/2-opt 的研究概念。其性能描述没有原始实验数据可供本次复算。提取文本存为 `sources/abstract.txt`。 |

## 源码查找结果与边界

Drive 目标目录及 paper01 所在现行 Research-IP 目录均已列举。还检查了用户的 Google Drive 实际本地同步目录，搜索 UAV、AGV、源码、ZIP、Python、MATLAB、notebook、C++、JavaScript、Java、RAR、7z 等文件名／扩展名。没有找到研究调度源码；目标设计包不是算法项目。以上仅说明本次可访问范围内未取得代码，不证明代码从未存在。没有读取无关申请人个人材料或归档旧 CV 内容。

因此：本次实现 **单独的演示规划器**，不是原研究源码复现；原研究硬／软窗口、罚项、GA 编码、2-opt 和作者代码职责仍保持未确认。原资料、共享设置及目录组织未被改动。

## 可复查的设计决定

| 决定 | 依据 | 本次实现及限制 |
| --- | --- | --- |
| Hard arrival / integer seconds | spec03 §5 | 端点含等号；在仓库延后出发；到达、服务开始、结束、返仓独立字段；UI 只做格式化。 |
| 单任务单趟、多趟串行 | spec03 §5、spec02 R08 | 载荷取任务重量；周转累积；没有多节点合并优化、拆单或空地接力。 |
| 演示搜索策略 | spec02 允许单独演示规划器 | 新增 earliest deadline first → earliest feasible arrival，平局按返仓时间、车辆 ID；明确不同于未知原始启发式和 GA。 |
| 独立校核 | spec02 D10、spec03 §4–5 | 从快照输入重算所有秒值与约束；检查任务覆盖／重复／完成历史／必需字段，失败不可批准。 |
| 版本／授权 | spec03 §2 | 输入与运行版本、SHA-256 派生快照 ID、计划 ID、批准范围、匿名标签；后端原子校验版本与状态。 |
| 异常恢复 | spec02 D07–D11 | 全局暂停、旧批准失效、剩余任务重排、新方案再批准；未完成行程按仓库检查点教学回滚，时钟不倒退。 |
| 可见未分配 | spec03 §5.2 | 具体原因＋所有检查证据＋下一步；正式 ETA 留空；零分配禁批，不宣称证明数学无解。 |
| 持久化 | 服务契约的可运行实现选择 | 单机 JSON 原子文件与串行写入；每个场景、批准和事件可导出；匿名单一工作区，没有多用户认证或设备接入。 |
| 可复审历史 | spec03 §2–3 | 保存旧快照、已完成任务要求、失效批准；重置先归档；历史只读。 |

上述实现是本次辅助开发，不能写成 Peiming 在 2025 年独立编写的系统或已发生的用户访谈／部署成果。spec02 R01–R09 个人取舍确认栏仍留待本人记录。软件契约测试与浏览器开发验证不等同于用户研究。

## 精确复算

内部 t=0 对应 09:00，往返距离对称。

| 任务 | 车辆 / 趟 | depart | arrival | service end | return | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | UAV-01 / Trip1 | 0 | 120 | 180 | 300 | 到达 09:02，返仓 09:05 |
| T02 | AGV-01 / Trip1 | 0 | 240 | 360 | 600 | 到达 09:04，返仓 09:10 |
| T03 | AGV-01 / Trip2 | 720 | 1080 | 1200 | 1560 | 周转 120s；到达 09:18，返仓 09:26 |
| T04 | — | — | — | — | — | 25kg > 2kg / 20kg；PAYLOAD_EXCEEDED |

09:00 UAV 不可用后，T01 对 AGV 最早到达为 360s（09:06），超过 300s（09:05）；该值只作为检查证据，不作为正式 ETA。T02/T03 保持可行，T04 仍超载。正好等于窗口端点的整数秒算例也已验证。

## 验收与复核入口

- `tests/service.test.mjs` 的 13 项测试覆盖 A01–A12、单趟返仓、班次、仓库等待、周转、不可行有限退出、候选缺字段、失败状态、批准／启动重复调用和归档。
- `tests/api.test.mjs` 通过真实子进程 HTTP 服务验证后端拒绝无批准启动、部分批准必填、运行检查点落盘、重启 Paused→Resume、Delivered 保留、异步并发写入冲突、导出、跨源写入拒绝和静态路径约束。
- 浏览器独立测试实例使用单独数据目录，验证部分计划需要勾选与二次确认；故障后旧批准失效、T01 留空 ETA、新建议重新批准；恢复后正确显示部分结束。开发控制台未发现 error / warn。
- 浏览器还验证反向时间窗保存失败且错误留在弹层；有效窗口编辑使旧方案及批准失效，历史候选继续显示其原始快照窗口。Keep tasks unassigned 已确认保存待办事件。
- 运行截图：`artifacts/plan-review.jpg`、`artifacts/execution-monitor.jpg`。它们是本次真实原型界面，不是原研究系统截图。

## 后续原研究适配入口

取得代码、原输入、依赖和运行日志后，按 spec01 K01–K08、K11 核查真实契约。用一个适配器返回 candidate 的 assignments / unassigned；仍经独立校核和快照安装，不将缺失字段补为零。多节点、软窗或新的能源／成本模型必须新增 rule profile 和独立验证器，改变配置使旧计划及批准失效；不能直接把 demo-v1 的可行性解释用于原模型。
