# frontend/src/
> L2 | 父级: ../CLAUDE.md

成员清单
api.js: API 客户端，统一 Bearer seller token、JSON 解析、PUT/PATCH/POST 写操作与错误归一。
App.jsx: React 工作台组合根，承载设计稿对齐的深色侧栏、玻璃顶栏、首页运营卡片、收件箱、客户、审批、通知、设置和 demo 操作。
catalog.jsx: 产品配置域组件，承载设计稿对齐的产品库标题/搜索工具、价格规则编辑/版本查看与渠道凭据轮换。
design_pages.jsx: 设计稿补齐页，承载报价规则、数据看板与移动端轻量接管三个离线原型独立视图。
forms.js: 表单 payload 归一层，把 FormData 转成后端 schema 接受的最小 JSON。
main.jsx: React 启动入口，把 App 挂载到 DOM。
styles.css: 工作台样式，复刻离线设计稿的墨蓝侧栏、#1F5C8C 主色、浅灰工作区、白卡片、状态色与桌面/窄屏响应式规则。
ui.jsx: 通用 UI 基元层，提供 panel、rows、form、field、metric、icon button 与 code block，并承载标题副文案、右侧动作、KPI delta。

架构边界
src/ 只表达前端状态和交互；后端事实来自 api.js；配置表单归一进入 forms.js，只提交后端 schema 接受的最小字段；危险动作必须调用 approvals API，不在前端伪造发送结果；样式保持操作型密度，避免营销页结构。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
