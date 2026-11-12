# 数据模型

## IssueRecord

机器约束由 schema.validate 实现。

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| sender | string | 非空 |
| timestamp | string | UTC 日期时间 YYYY-MM-DDTHH:mm:ssZ，真实有效日期 |
| text | string | 标题与正文，正文抓取时截断到 2000 字符 |
| channel | string | 非空仓库标识 |
| thread_id | integer | 正整数，不接受 bool |
| labels | string[] | 全部为字符串 |
| state | string | open 或 closed |
| comments_count | integer | 非负，不接受 bool |
| url | string | 可选的公开 Issue 地址 |

## RiskHit

rule 为 unaddressed_security、severity_keyword_match 或 fast_escalating_regression；thread_id 为 Issue 编号；evidence 为规则证据；url 为来源地址。同一 Issue 可以返回多个命中。

## RetrievalHit

text 为原文片段，meta.source 为文档文件名，score 为 TF-IDF 余弦相似度。当前文本分词为英文及数字。问答返回含来源的文本，不输出伪造置信度。

## 数据生命周期

优先加载 data/issues_clean.jsonl；不存在时读取 data/sample_issues.jsonl。加载时逐条验证，错误包含行号。演示固定读取内置快照。原始数据、运行输出和 .env 不纳入交付包。

## Workspace 展示数据

/workspace 返回 kind、title、records、tasks、risks、groups、briefs、documents、period_start、period_end、projects。records 统一包含 id、title、text、author、time、channel、labels、state、url；documents 包含 name 与 title；projects 包含 id、title 与 url。来源正文由 /workspace/documents/{name} 返回 name、text。

前端完成记录以任务文本、负责人和日期为键。导出 JSON 中 review_state 包含 task 与 completed；该字段表示当前浏览器的跟进状态。
