/**
 * [INPUT]: 依赖 React JSX 与 lucide-react Plus 图标
 * [OUTPUT]: 对外提供 Panel、Rows、StatusRows、ApiForm、Field、JsonField、Metric、IconButton、CodeBlock
 * [POS]: frontend/src 的通用 UI 基元层，承载标题副文案、右侧动作与 KPI delta 等设计稿通用结构
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

import { Plus } from "lucide-react";

export function Panel({ title, subtitle, action, children, span = "" }) {
  return (
    <section className={`panel ${span}`}>
      <header>
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action && <div className="panel-action">{action}</div>}
      </header>
      {children}
    </section>
  );
}

export function Rows({ items = [], empty, render }) {
  if (!items.length) return <p className="empty">{empty}</p>;
  return <div className="rows">{items.map((item) => <div className="row" key={item.id || item.name || item.title}>{render(item)}</div>)}</div>;
}

export function StatusRows({ rows = [], empty = "暂无数据。" }) {
  if (!rows.length) return <p className="empty">{empty}</p>;
  return <div className="status-rows">{rows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>;
}

export function ApiForm({ children, submitLabel, onSubmit, testId }) {
  return (
    <form
      className="api-form"
      data-testid={testId}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(new FormData(event.currentTarget));
      }}
    >
      {children}
      <button className="primary" type="submit" data-testid={testId ? `${testId}-submit` : undefined}>
        <Plus size={17} />
        {submitLabel}
      </button>
    </form>
  );
}

export function Field({ label, name, type = "text", ...props }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input name={name} type={type} {...props} />
    </label>
  );
}

export function JsonField({ label, name, defaultValue }) {
  return (
    <label className="field">
      <span>{label}</span>
      <textarea name={name} defaultValue={JSON.stringify(defaultValue, null, 2)} rows={4} />
    </label>
  );
}

export function Metric({ label, value, tone, delta }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {delta && <em>{delta}</em>}
      <i className="sparkline" aria-hidden="true" />
    </div>
  );
}

export function IconButton({ label, icon: Icon, ...props }) {
  return (
    <button className="icon-button" aria-label={label} title={label} {...props}>
      <Icon size={18} />
    </button>
  );
}

export function CodeBlock({ value }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}
