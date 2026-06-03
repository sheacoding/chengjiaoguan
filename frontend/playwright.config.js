/**
 * [INPUT]: 依赖 @playwright/test、FastAPI 本地启动命令与 Vite dev server
 * [OUTPUT]: 对外提供 Playwright E2E 配置，自动启动 API/前端工作台并运行桌面/移动项目
 * [POS]: frontend 的浏览器测试边界，验证公开 API 经过真实 UI 被正确消费
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

import { defineConfig } from "@playwright/test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "..");
const python = process.env.CLOSER_E2E_PYTHON || ".venv/bin/python";
const browserChannel = process.env.PLAYWRIGHT_BROWSER_CHANNEL || "chrome";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: {
    timeout: 8_000,
  },
  fullyParallel: false,
  reporter: process.env.CI ? [["dot"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    channel: browserChannel,
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: {
        viewport: { width: 1280, height: 900 },
      },
    },
    {
      name: "mobile",
      use: {
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 2,
        hasTouch: true,
        isMobile: true,
      },
    },
  ],
  webServer: [
    {
      command: `${python} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: repoRoot,
      url: "http://127.0.0.1:8000/api/v1/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --port 5173",
      cwd: here,
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
