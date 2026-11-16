# 话单计费深度登记

规模：中型。使用者：通信结算分析员。核心规则：分片先求时间区间并集，再对整个会话向上取整分钟；间隙不收费，阶梯资费使用会话开始时的唯一生效版本。

## 功能模块
| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 话单接收 | 接收文件并保留逻辑与物理行号 | `/intake`、`/api/intake` | `app/modules/intake/reader.py` `app/modules/intake/service.py` | `tests/test_intake.py` |
| M2 资费契约 | 归一序号时区并校验区域 | `/contract`、`/api/contract` | `app/modules/contract/normalize.py` `app/modules/contract/service.py` | `tests/test_contract.py` |
| M3 分片拼接 | 按会话去重并求区间并集 | `/model`、`/api/model` | `app/modules/model/stitch.py` `app/modules/model/service.py` | `tests/test_model.py` |
| M4 计费重算 | 按并集秒取整并阶梯计费 | `/calculate`、`/api/calculate` | `app/modules/calculate/tariff.py` `app/modules/calculate/service.py` | `tests/test_calculate.py` |
| M5 坏单隔离 | 筛查拒收原因与原始证据 | `/quarantine`、`/api/quarantine` | `app/modules/quarantine/diagnose.py` `app/modules/quarantine/service.py` | `tests/test_quarantine.py` |
| M6 账单勾稽 | 计费金额与供应商账单逐会话对照 | `/reconcile`、`/api/reconcile` | `app/modules/reconcile/compare.py` `app/modules/reconcile/service.py` | `tests/test_reconcile.py` |
| M7 批次复核 | 摘要幂等归档与版本复核 | `/batches`、`/api/batches` | `app/modules/batches/review.py` `app/modules/batches/service.py` | `tests/test_batches.py` |

## 陷阱登记
| TRAP | 现象 | 朴素实现会怎样 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | 旧话单编码 | 重复计费或任意选择数据 | 确定性拒收并保留逐行来源 | `app/modules/intake/reader.py` | `tests/test_intake.py::test_legacy` |
| TRAP-02 | BOM表头 | 重复计费或任意选择数据 | 确定性拒收并保留逐行来源 | `app/modules/intake/reader.py` | `tests/test_intake.py::test_bom` |
| TRAP-06 | 全角序号 | 重复计费或任意选择数据 | 确定性拒收并保留逐行来源 | `app/modules/contract/normalize.py` | `tests/test_contract.py::test_fullwidth_sequence` |
| TRAP-07 | 空值序号 | 重复计费或任意选择数据 | 确定性拒收并保留逐行来源 | `app/modules/contract/service.py` | `tests/test_contract.py::test_missing` |
| TRAP-08 | 用户前导零 | 重复计费或任意选择数据 | 确定性拒收并保留逐行来源 | `app/modules/contract/service.py` | `tests/test_contract.py::test_leading_zero` |
| TRAP-10 | 分币精度 | 重复计费或任意选择数据 | 确定性拒收并保留逐行来源 | `app/modules/calculate/tariff.py` | `tests/test_calculate.py::test_decimal_exact` |
| TRAP-14 | 同序分片冲突 | 重复计费或任意选择数据 | 确定性拒收并保留逐行来源 | `app/modules/model/service.py` | `tests/test_model.py::test_conflict_isolate_whole_session` |
| TRAP-23 | 相邻端点 | 重复计费或任意选择数据 | 确定性拒收并保留逐行来源 | `app/modules/model/stitch.py` | `tests/test_model.py::test_adjacent_half_open` |
| TRAP-25 | 资费版本重叠 | 重复计费或任意选择数据 | 确定性拒收并保留逐行来源 | `app/modules/calculate/tariff.py` | `tests/test_calculate.py::test_overlapping_version` |
| TRAP-26 | 陈旧复核 | 重复计费或任意选择数据 | 确定性拒收并保留逐行来源 | `app/modules/batches/service.py` | `tests/test_batches.py::test_stale_review` |

## 对账规则
输入分片=计费会话中的有效分片+隔离分片+空行。原始去重分片秒=并集有效秒+重叠剔除秒。供应商金额减重算金额逐会话解释；无法匹配的账单单列，不自动当作零。

## 流水线与反例
标准会话3片原始100秒，并集90秒，间隙50秒；按跨度会错误收3分钟，正确只收2分钟。计费跨月用带偏移时间作区间并集；资费边界为半开区间，有版本重叠直接隔离该会话的全部片段。事务写入完整批次；摘要含资费与供应商账单，重复批次不追加。复核乐观锁拒绝陈旧提交。

## 已知不覆盖
不处理跨运营商实时漫游清分，不跨币种换汇。每分片最长24小时。分片缺序将整会话隔离，不能推断未到达的时长。