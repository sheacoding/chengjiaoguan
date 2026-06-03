# Visual QA
> L3 | 父级: ./CLAUDE.md

<!--
/**
 * [INPUT]: 依赖 Closer 工作台离线设计稿、frontend 工作台、Playwright 浏览器截图、/demo/seed 与 /webhooks/site_form 公开 API
 * [OUTPUT]: 对外提供设计稿对齐、桌面/移动视觉 QA 证据、截图路径与剩余视觉风险
 * [POS]: docs 的前端视觉证明镜像，把生产部署级视觉走查从口头判断转成可复核证据
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
-->

## 场景

视觉 QA 使用默认租户 `seller:1`，通过公开 API 注入 24 条长文本 site_form 询盘，再打开 React/Vite 工作台客户页检查密集列表。

## 证据

- 设计稿参考截图：`/private/tmp/closer-design-reference.png`
- 重构后工作台桌面截图：`/private/tmp/closer-redesign-dashboard-desktop.png`
- 重构后报价规则桌面截图：`/private/tmp/closer-redesign-quote-rules-desktop.png`
- 重构后数据看板桌面截图：`/private/tmp/closer-redesign-analytics-desktop.png`
- 重构后移动端页面桌面截图：`/private/tmp/closer-redesign-mobile-page-desktop.png`
- 重构后移动视口截图：`/private/tmp/closer-redesign-dashboard-mobile.png`
- 桌面截图：`/private/tmp/closer-visual-desktop.png`
- 移动截图：`/private/tmp/closer-visual-mobile.png`
- in-app browser 截图：`/private/tmp/closer-redesign-browser.png`，已验证窄视口 `scrollWidth == clientWidth`

## 设计稿对齐

离线设计稿 `Closer 工作台（离线版）.html` 的关键视觉 token 已进入前端机器相：主色 `#1F5C8C`、深色侧栏 `#14222F`、浅灰工作区 `#F5F7F9`、白色卡片、绿色/橙色/红色状态语义、Inter/PingFang 字体与 8px 栅格。

工作台首页已对齐设计稿的信息骨架：深色侧栏、顶栏搜索、配置完成度卡、卖家身份区、欢迎区、四张 KPI 卡、待处理队列、近 7 日趋势与实时询盘流。产品库页补齐设计稿式标题、搜索和导入工具行；报价规则、数据看板、移动端三个设计稿独立导航页已落地。

## 指标

| 视口 | clientWidth | scrollWidth | rowCount | rowsClientHeight | rowsScrollHeight | token |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| redesign dashboard desktop 1440x900 | 1440 | 1440 | - | - | - | `#1F5C8C` / `#14222F` |
| redesign quote rules desktop 1440x900 | 1440 | 1440 | - | - | - | `#1F5C8C` / `#14222F` |
| redesign analytics desktop 1440x900 | 1440 | 1440 | - | - | - | `#1F5C8C` / `#14222F` |
| redesign mobile page desktop 1440x900 | 1440 | 1440 | - | - | - | `#1F5C8C` / `#14222F` |
| redesign dashboard mobile 390x844 | 390 | 390 | - | - | - | `#1F5C8C` / `#14222F` |
| desktop 1280x900 | 1280 | 1280 | 20 | 576 | 2015 |
| mobile 390x844 | 390 | 390 | 20 | 540 | 3526 |

判定：重构后桌面与移动均无横向溢出；客户列表在 20 条长文本数据下产生纵向滚动；按钮与长公司名在窄屏自然折行；关键色彩与导航语义已和设计稿同构。

## 剩余风险

这次覆盖的是本地生产形态视觉 QA，不等于真实线上环境彩排。真实域名、生产 API、真实监控、真实渠道凭据与用户浏览器组合仍需部署后复核。
