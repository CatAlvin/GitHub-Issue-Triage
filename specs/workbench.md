# 前端工作台

## GT-UI01 工作台

现有 FastAPI 直接提供根路径页面和 /assets/ 静态资源，不增加独立业务服务。页面按概览、Issue 记录、风险关注、知识问答组织。快照日期、数据量及分布来自 /workspace。

## GT-UI02 接口

- GET /workspace：当前数据、任务、风险、来源清单与工作台配置。
- POST /workspace/brief：按当前数据生成结构化简报，参数 days 为 1 至 90。
- POST /workspace/ask：输入 question 长度 3 至 2000；返回 answer、sources 和 refused。
- GET /workspace/documents/{name}：仅访问项目知识库中列出的 Markdown 文件，返回正文。
- / 和 /assets/ 提供公开界面；配置 SERVICE_API_KEY 后，业务接口仍验证 Bearer 令牌。

模型调用仅由明确的生成或问答操作触发。页面初次加载不调用模型。截图与功能验证使用 offline。

## GT-UI03 状态与展示

搜索、状态筛选、空结果、读取失败与重试、生成中反馈均须可操作。Issue 详情按纯文本展示；知识回答与来源支持标题、列表和代码排版，源 HTML 转义，链接仅允许 HTTP(S)。知识问答失败时给出可重试提示，资料无匹配时引导重新提问。

Issue 详情保留原始链接，仅允许 https GitHub 链接。窗口摘要使用快照最新时间加一天，日期在页面展示。

## 验收

- GT-UI-AC01：页面可加载，所有可见控件有实际行为。
- GT-UI-AC02：搜索与筛选结果来自当前数据，导出内容与当前项目一致。
- GT-UI-AC03：相关问答可打开来源，无关问题显示重新提问入口。
- GT-UI-AC04：深浅主题、键盘操作、移动布局和详情关闭通过浏览器检查。
- GT-UI-AC05：现有业务回归及接口契约检查继续通过，压缩包包含静态资源。

## 任务

| 任务 | 输入 | 输出 | 验收 |
| --- | --- | --- | --- |
| UI-T01 | GT-UI01/02 | workbench_api.py、API 挂载 | API 自动测试 |
| UI-T02 | GT-UI03 | web/index.html、app.css、app.js、markdown.js | 浏览器交互检查 |
| UI-T03 | 全部 UI 验收 | 同步脚本、打包更新、验证记录 | 契约与完整回归 |
