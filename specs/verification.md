# 验证记录

日期：2026-11-03。环境：Windows、Python 3.12.1、APP_MODE=offline。

## 结果

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 自动测试 | 16/16 通过 | python -m unittest discover -s tests -v |
| HTTP / MCP 契约 | 一致 | python scripts/contracts.py |
| 固定快照演示 | 通过 | python demo.py；25 条 Issue，参考时间 2026-09-25T00:01:16Z |
| 本地 HTTP 与 HTTP MCP | 通过 | python scripts/smoke_http.py；真实 Uvicorn、鉴权、MCP 初始化和工具调用 |
| 干净依赖安装 | 通过 | 新建 venv，从 requirements.txt 安装；pip check 无依赖冲突 |
| 独立压缩包 | 通过 | 37 个文件逐项 SHA-256 校验；解压后重新执行 verify.py 与 smoke_http.py |

## 验收追踪

| 需求 / 验收 | 测试证据 |
| --- | --- |
| GT-01 / GT-AC01 | test_bundled_schema、test_invalid_types_and_dates、test_loading_invalid_record_reports_line |
| GT-02 / GT-AC02 | test_window_order_boundaries_and_future、test_summary_cap_selects_latest、test_summary_real_offline_path |
| GT-03 / GT-AC03 | test_risk_time_boundaries、test_risk_requires_independent_signals |
| GT-04 / GT-AC04 | test_citation_and_refusal |
| GT-05 至 GT-07 / GT-AC05 | test_real_stdio_handshake_and_tool_calls、test_token_auth、test_slack_dedup_and_thread_reply、smoke_http |
| GT-AC06 | scripts/contracts.py 对比 OpenAPI 与五个 MCP 工具 Schema |

GT-T01 至 GT-T06 已实现并通过上述验证。字段验证、未来时间处理和最新 40 条选择均有对应回归用例。

## 过程与限制

Windows 沙箱的 asyncio 回环初始化曾阻塞；在允许本机回环的环境中完成相同测试和实际协议检查。依赖缓存不完整，改为在新虚拟环境中从 PyPI 安装后重跑成功。新解析的 Starlette 1.10.0 对测试客户端的 httpx 发出弃用提示，未影响本次测试结果。

本次未调用付费模型，未连接真实 Slack，未构建 Docker 镜像或部署公网服务。在线模型回答的事实质量、负载能力和真实用户效果未验收。内置快照的零风险命中只描述该数据，不代表规则召回率。

## 2026-11-05 前端工作台验收

完整测试 21/21 通过，包含新增 5 项工作台接口检查。运行时 HTTP 与 MCP 契约已重新导出并检查一致。GT-UI-AC01 至 GT-UI-AC04 通过浏览器检查：搜索筛选、详情关闭、相关问答与来源、简报生成、项目切换、键盘焦点、主题与窄屏布局。

静态资源随独立项目导出。scripts/smoke_http.py 同时验证页面、资源、工作台鉴权和来源问答。
