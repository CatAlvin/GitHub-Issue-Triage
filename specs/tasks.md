# 实施任务

| 任务 | 输入 | 产出 | 依赖 | 验收 |
| --- | --- | --- | --- | --- |
| GT-T01 数据契约 | GT-01、data-models | schema.py、ingest.py | 无 | GT-AC01 |
| GT-T02 摘要与模型模式 | GT-02、GT-06、ADR-003 | assistant.py、common/ | GT-T01 | GT-AC02 |
| GT-T03 风险规则 | GT-03、ADR-002 | risk_rules.py | GT-T01 | GT-AC03 |
| GT-T04 知识问答 | GT-04、ADR-001 | assistant.py、kb/ | 无 | GT-AC04 |
| GT-T05 对外接口 | GT-05、GT-07、api-spec | api.py、mcp_server.py、slack_bot.py | GT-T02 至 GT-T04 | GT-AC05 |
| GT-T06 工程验证 | 全部验收标准 | tests/、scripts/、verification.md | GT-T05 | GT-AC01 至 GT-AC06 |
| GT-T07 前端工作台 | [workbench](workbench.md) | workbench_api.py、web/、test_workbench.py | GT-T05 | GT-UI-AC01 至 GT-UI-AC05 |

执行状态和命令结果见 [verification.md](verification.md)。外部 Slack 接入、真实模型质量及公网部署分别验收，不由离线测试推定。
