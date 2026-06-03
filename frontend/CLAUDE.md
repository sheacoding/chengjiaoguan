# frontend/
> L2 | 父级: ../CLAUDE.md

成员清单
index.html: Vite HTML 入口，挂载 React 工作台根节点。
package.json: 前端依赖与脚本配置，定义 dev/build/preview 命令。
package-lock.json: npm 锁文件，固定 React/Vite/lucide 依赖图与安全审计基线。
playwright.config.js: Playwright 配置，启动 FastAPI 与 Vite 并使用本地 Chrome channel 执行桌面/移动浏览器 E2E。
vite.config.js: Vite 配置，提供 React 插件与 /api 到后端的本地代理。
e2e/: Playwright 浏览器测试，验证工作台主链路 UI 到 API 接缝与窄屏无横向溢出。
src/: React 工作台源码，承载 API 客户端、页面组合根与样式。

架构边界
frontend/ 是前端机器相，只调用公开 `/api/v1` HTTP API；不直接访问数据库，不复制后端业务规则，不绕过审批和租户鉴权。开发期通过 Vite proxy 指向 FastAPI，生产期可用 `VITE_API_BASE_URL` 指向部署后的 API。

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
