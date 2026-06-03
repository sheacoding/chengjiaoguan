/**
 * [INPUT]: 依赖 React、ReactDOM、App 与 styles.css
 * [OUTPUT]: 对外启动 CloserWorkBench React 应用
 * [POS]: frontend/src 的浏览器入口，只负责 DOM 挂载
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
