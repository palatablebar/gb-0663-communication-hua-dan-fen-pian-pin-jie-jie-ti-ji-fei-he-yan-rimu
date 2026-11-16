# 通信话单分片拼接与阶梯计费核验

为通信结算分析员提供话单接收、资费契约、分片拼接、计费重算、坏单隔离、账单勾稽和批次复核七个模块。区间并集后按会话向上取整分钟，排除重复与间隙；资费按生效版本分阶梯计算，Decimal精确到分。

## 启动

```sh
docker compose up --build -d
docker compose config --quiet
docker compose exec -T app pytest -q
```

访问 http://localhost:18202 ，首次自动运行脏话单。工具条可切换标准与旧编码样例。话单接收页可粘贴自有CSV；计费页可筛选会话。坏单隔离导出CSV，完整API结构见 `/docs`。每个计算模块可通过POST模块API独立试跑；`POST /api/runs`完成持久化运行。

## 演示

1. 标准话单下会话有效90秒、计费2分钟。
2. 分片拼接页查看10秒重叠与50秒间隙的剔除证据。
3. 切换脏话单，C00001冲突整会话隔离、C00090缺序隔离。
4. 账单勾稽逐会话比较供应商费用，缺账单保持未知。
5. 重跑不追加批次；复核使用当前版本，旧版请求返回409。

SQLite数据保存在records命名卷。执行 `docker compose down`停止服务保留数据；确认演示数据无需保留后可使用 `docker compose down -v`清空本项目记录。

`app/modules/`为业务模块，`sample_data/`为话单、资费与账单，`tests/`包含模块及端到端测试。字段与边界见 `docs/DATA-DICTIONARY.md`，测试映射见 `docs/DEPTH.md`。不处理跨币种清分、不推断缺失片段。
