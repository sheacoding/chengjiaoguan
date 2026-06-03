/**
 * [INPUT]: 依赖 lucide-react 图标、frontend/src/ui.jsx 基元、dashboard metrics、pricingRules 与 approvals 数据
 * [OUTPUT]: 对外提供 QuoteRulesPage、AnalyticsPage、MobilePreviewPage 三个设计稿独立页面
 * [POS]: frontend/src 的设计稿补齐层，承载离线工作台中的报价规则、数据看板与移动端轻量接管视图
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

import { Bell, Check, Clock, Download, MessageSquare, Shield, SlidersHorizontal, Smartphone, Target, TrendingUp } from "lucide-react";
import { Metric, Panel, Rows, StatusRows } from "./ui.jsx";

export function QuoteRulesPage({ pricingRules }) {
  const rules = pricingRules?.items || [];
  const first = rules[0] || {};
  const floor = first.floor_price ?? "3.00";
  const margin = first.margin_rate ?? "0.25";
  const validDays = first.valid_days ?? 14;
  return (
    <section className="rules-page">
      <div className="page-heading">
        <div>
          <h2>报价规则</h2>
          <p>配置一次，Agent 即可按规则自动报价，底价红线永远留给人工拍板。</p>
        </div>
        <button className="primary"><Check size={16} />保存规则</button>
      </div>
      <div className="split">
        <div className="stack">
          <Panel title="基础定价" subtitle={`Product #${first.product_id || "-"} · / 套`} action={<SlidersHorizontal size={17} />}>
            <div className="rule-grid">
              <RuleBox label="底价红线" value={floor} prefix="$" tone="red" />
              <RuleBox label="目标利润率" value={margin} suffix="%" tone="green" />
              <RuleBox label="报价有效期" value={validDays} suffix="天" tone="blue" />
              <RuleBox label="汇率来源" value="人工确认" tone="amber" />
            </div>
          </Panel>
          <Panel title="阶梯价" subtitle="设计稿强调用阶梯配置消除临时判断">
            <Rows
              items={rules.slice(0, 4)}
              empty="暂无价格规则。"
              render={(rule) => (
                <div className="stream-row">
                  <span>Rule #{rule.id}</span>
                  <strong>Product #{rule.product_id || "-"}</strong>
                  <p>{rule.currency} floor {rule.floor_price} · margin {rule.margin_rate ?? "-"}</p>
                  <em>{rule.status || "active"}</em>
                </div>
              )}
            />
          </Panel>
        </div>
        <Panel title="报价预览" subtitle="低于底价时必须转人工" action={<Shield size={17} />}>
          <div className="quote-preview">
            <span className="badge badge-red">底价护栏</span>
            <strong>自动报价前检查 MOQ、阶梯价、汇率缓存与底价。</strong>
            <StatusRows
              rows={[
                ["建议单价", `${first.currency || "USD"} ${floor}`],
                ["有效期", `${validDays} 天`],
                ["规则数量", rules.length],
                ["低价策略", "创建 approval"],
              ]}
            />
          </div>
        </Panel>
      </div>
    </section>
  );
}

export function AnalyticsPage({ metrics }) {
  const approval = metrics?.approval || {};
  const delivery = metrics?.delivery || {};
  const followup = metrics?.followup || {};
  return (
    <section className="analytics-page">
      <div className="page-heading">
        <div>
          <h2>数据看板</h2>
          <p>用带来成交而非回复快衡量 Agent 的价值。</p>
        </div>
        <button><Download size={16} />导出</button>
      </div>
      <div className="metrics kpi-grid">
        <Metric label="今日新询盘" value={metrics?.today_inquiries ?? 0} tone="blue" delta="+3" />
        <Metric label="待审批" value={approval.pending ?? 0} tone="amber" delta="人工" />
        <Metric label="投递失败" value={delivery.failed ?? 0} tone="red" delta="重试" />
        <Metric label="待跟进" value={followup.due ?? 0} tone="green" delta="due" />
      </div>
      <div className="dashboard-grid">
        <Panel title="转化漏斗" subtitle="询盘 → 报价 → 审批 → 成交" action={<Target size={17} />}>
          <div className="funnel">
            {[
              ["询盘", metrics?.pipeline?.total ?? metrics?.today_inquiries ?? 0, 100],
              ["报价", metrics?.quotation?.total ?? 0, 62],
              ["审批", approval.pending ?? 0, 28],
              ["成交", metrics?.conversion ?? 0, 23],
            ].map(([label, value, pct]) => (
              <div key={label}>
                <span>{label}</span><strong>{value}</strong><i style={{ width: `${pct}%` }} />
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="近 30 天趋势" subtitle="询盘量 vs 成交" action={<TrendingUp size={17} />}>
          <div className="trend-chart" aria-hidden="true">
            {[42, 58, 39, 72, 51, 33, 67].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}
            <svg viewBox="0 0 240 80" preserveAspectRatio="none">
              <polyline points="0,58 40,50 80,60 120,44 160,52 200,66 240,43" />
            </svg>
          </div>
          <div className="legend"><span>询盘</span><span>成交</span></div>
        </Panel>
      </div>
    </section>
  );
}

export function MobilePreviewPage({ approvals }) {
  const pending = approvals?.items?.[0];
  return (
    <section className="mobile-page">
      <div className="page-heading">
        <div>
          <h2>移动端 · 轻量接管</h2>
          <p>转人工提醒 → 快速查看 → 一键接管 / 批准报价。</p>
        </div>
      </div>
      <div className="mobile-layout">
        <div className="phone-frame">
          <div className="phone-screen">
            <header><span>9:41</span><Smartphone size={15} /></header>
            <div className="phone-alert">
              <Bell size={18} />
              <strong>待你处理</strong>
              <p>{pending?.summary || pending?.reason || "Garden Living BV 触及底价红线，等待人工确认。"}</p>
              <button className="primary">查看详情</button>
              <button>一键接管</button>
            </div>
          </div>
        </div>
        <div className="stack mobile-copy">
          {[
            [Bell, "推送提醒", "护栏触发或大单时，提醒直达手机。"],
            [MessageSquare, "快速查看", "一屏看清客户分级、对话摘要与 AI 建议。"],
            [Clock, "一键处理", "批准建议价、人工接管，或者守住底价。"],
          ].map(([Icon, title, desc]) => (
            <Panel key={title} title={title} subtitle={desc} action={<Icon size={17} />} />
          ))}
        </div>
      </div>
    </section>
  );
}

function RuleBox({ label, value, prefix = "", suffix = "", tone = "blue" }) {
  return (
    <div className={`rule-box ${tone}`}>
      <span>{label}</span>
      <strong>{prefix}{value}{suffix}</strong>
    </div>
  );
}
