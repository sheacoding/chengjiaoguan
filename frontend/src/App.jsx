/**
 * [INPUT]: 依赖 React hooks、lucide-react 图标、createApiClient、Products 域组件与离线设计稿信息架构
 * [OUTPUT]: 对外提供 App 组件，展示设计稿对齐的 Closer 工作台外壳、首页、Demo 编排、审批发送、行级审批与配置数据
 * [POS]: frontend/src 的页面组合根，连接后端 /api/v1 资源与《成交官》操作型 SaaS UI
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  Bell,
  Bot,
  Check,
  ClipboardList,
  Archive,
  Eye,
  Globe2,
  Inbox as InboxIcon,
  LineChart,
  Package,
  Play,
  RefreshCw,
  Send,
  Settings,
  ShieldCheck,
  Search,
  SlidersHorizontal,
  Smartphone,
  TrendingUp,
  Zap,
  Users,
} from "lucide-react";
import { createApiClient } from "./api.js";
import { Products } from "./catalog.jsx";
import { AnalyticsPage, MobilePreviewPage, QuoteRulesPage } from "./design_pages.jsx";
import { channelPayload, pricingPayload, productPayload, safeGet, settingsPayload } from "./forms.js";
import { ApiForm, CodeBlock, Field, IconButton, Metric, Panel, Rows, StatusRows } from "./ui.jsx";

const NAV = [
  { id: "dashboard", label: "工作台", testLabel: "看板", icon: BarChart3 },
  { id: "inbox", label: "询盘收件箱", testLabel: "收件箱", icon: ClipboardList },
  { id: "customers", label: "客户档案", testLabel: "客户", icon: Users },
  { id: "products", label: "产品库", testLabel: "产品", icon: Package },
  { id: "quoteRules", label: "报价规则", testLabel: "报价规则", icon: SlidersHorizontal },
  { id: "analytics", label: "数据看板", testLabel: "数据看板", icon: LineChart },
  { id: "mobile", label: "移动端", testLabel: "移动端", icon: Smartphone },
  { id: "settings", label: "设置", testLabel: "设置", icon: Settings },
];

const EMPTY = { items: [], total: 0 };
const LIST_PAGE_SIZE = 20;

export default function App() {
  const [sellerId, setSellerId] = useState(() => Number(localStorage.getItem("closer.sellerId") || 1));
  const [activeTab, setActiveTab] = useState("dashboard");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [demo, setDemo] = useState(null);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [quoteDetail, setQuoteDetail] = useState(null);
  const [data, setData] = useState({
    metrics: {},
    inquiries: EMPTY,
    approvals: EMPTY,
    customers: EMPTY,
    products: EMPTY,
    pricingRules: EMPTY,
    channels: EMPTY,
    notifications: EMPTY,
    readiness: {},
    settings: null,
    messages: EMPTY,
  });

  const api = useMemo(() => createApiClient({ sellerId }), [sellerId]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [metrics, inquiries, approvals, customers, products, pricingRules, channels, notifications, readiness, settings] = await Promise.all([
        api.get("/api/v1/dashboard/metrics"),
        api.get(`/api/v1/inquiries?page_size=${LIST_PAGE_SIZE}`),
        api.get("/api/v1/approvals"),
        api.get(`/api/v1/customers?page_size=${LIST_PAGE_SIZE}`),
        api.get(`/api/v1/products?page_size=${LIST_PAGE_SIZE}`),
        api.get("/api/v1/pricing-rules"),
        api.get("/api/v1/channels"),
        api.get(`/api/v1/notifications?status=unread&page_size=${LIST_PAGE_SIZE}`),
        api.get("/api/v1/ops/readiness"),
        safeGet(api, "/api/v1/settings", null),
      ]);
      setData((current) => ({ ...current, metrics, inquiries, approvals, customers, products, pricingRules, channels, notifications, readiness, settings }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    localStorage.setItem("closer.sellerId", String(sellerId));
    setSelectedCustomer(null);
    setQuoteDetail(null);
    loadAll();
  }, [sellerId, loadAll]);

  async function runDemoSeed() {
    await runAction("已生成 Demo 主链路数据", async () => {
      const payload = await api.post("/api/v1/demo/seed");
      setDemo(payload);
      await loadMessages(payload.conversation_id);
      await loadAll();
    });
  }

  async function approveDemo() {
    const approvalId = demo?.approval?.approval_id || data.approvals.items[0]?.id;
    if (!approvalId) {
      setError("没有可审批的 pending approval，先生成 Demo 数据。");
      return;
    }
    await runAction("审批已执行，消息已进入投递边界", async () => {
      await api.post(`/api/v1/approvals/${approvalId}/approve`);
      if (demo?.conversation_id) {
        await loadMessages(demo.conversation_id);
      }
      await loadAll();
    });
  }

  async function approveApproval(approvalId) {
    await runAction("审批已执行，消息已进入投递边界", async () => {
      await api.post(`/api/v1/approvals/${approvalId}/approve`);
      if (demo?.conversation_id) {
        await loadMessages(demo.conversation_id);
      }
      await loadAll();
    });
  }

  async function runWorkers() {
    await runAction("Workers 已运行", async () => {
      const workers = await api.post("/api/v1/workers/run-due");
      setDemo((current) => ({ ...(current || {}), workers }));
      await loadAll();
    });
  }

  async function createProduct(form) {
    await runAction("产品已创建", async () => {
      await api.post("/api/v1/products", productPayload(form));
      await loadAll();
    });
  }

  async function createPricingRule(form) {
    await runAction("价格规则已创建", async () => {
      await api.post("/api/v1/pricing-rules", pricingPayload(form));
      await loadAll();
    });
  }

  async function updatePricingRule(ruleId, form) {
    await runAction("价格规则已更新", async () => {
      await api.put(`/api/v1/pricing-rules/${ruleId}`, pricingPayload(form));
      await loadAll();
    });
  }

  async function loadPricingVersions(ruleId) {
    await runAction("价格规则版本已加载", async () => {
      const versions = await api.get(`/api/v1/pricing-rules/${ruleId}/versions`);
      setData((current) => ({ ...current, pricingVersions: versions, selectedPricingRuleId: ruleId }));
    });
  }

  async function createChannel(form) {
    await runAction("渠道已创建", async () => {
      await api.post("/api/v1/channels", channelPayload(form));
      await loadAll();
    });
  }

  async function rotateChannel(channelId) {
    await runAction("渠道凭据已轮换", async () => {
      await api.post(`/api/v1/channels/${channelId}/rotate-credentials`);
      await loadAll();
    });
  }

  async function saveSettings(form) {
    await runAction("设置已保存", async () => {
      await api.patch("/api/v1/settings", settingsPayload(form));
      await loadAll();
    });
  }

  async function markNotification(notificationId, status) {
    await runAction("通知状态已更新", async () => {
      await api.patch(`/api/v1/notifications/${notificationId}`, { status });
      await loadAll();
    });
  }

  async function openCustomer(customerId) {
    await runAction("客户档案已加载", async () => {
      const detail = await api.get(`/api/v1/customers/${customerId}`);
      setSelectedCustomer(detail);
      if (detail.quotations?.[0]?.id) {
        setQuoteDetail(await api.get(`/api/v1/quotations/${detail.quotations[0].id}`));
      } else {
        setQuoteDetail(null);
      }
    });
  }

  async function openQuotation(quotationId) {
    await runAction("报价详情已加载", async () => {
      setQuoteDetail(await api.get(`/api/v1/quotations/${quotationId}`));
    });
  }

  async function sendQuotation(quotationId) {
    await runAction("报价发送动作已提交", async () => {
      await api.post(`/api/v1/quotations/${quotationId}/send`);
      setQuoteDetail(await api.get(`/api/v1/quotations/${quotationId}`));
      await loadAll();
    });
  }

  async function loadMessages(conversationId) {
    if (!conversationId) return;
    const messages = await api.get(`/api/v1/conversations/${conversationId}/messages`);
    setData((current) => ({ ...current, messages }));
  }

  async function runAction(message, action) {
    setLoading(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(message);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const activeNav = NAV.find((item) => item.id === activeTab) || { ...NAV[0], label: "待我处理" };
  const pendingApprovalCount = data.approvals?.total ?? data.approvals?.items?.length ?? 0;
  const unreadNotificationCount = data.notifications?.total ?? data.notifications?.items?.length ?? 0;

  return (
    <div className="shell" id="app-shell">
      <aside className="side">
        <div className="brand">
          <span className="mark"><Check size={18} /></span>
          <div>
            <strong>Closer</strong>
            <span>成交官工作台</span>
          </div>
        </div>
        <nav className="nav">
          <span className="nav-section">工作区</span>
          {NAV.map((item) => (
            <button
              key={item.id}
              className={activeTab === item.id ? "active" : ""}
              aria-label={item.testLabel}
              onClick={() => setActiveTab(item.id)}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
              {item.id === "dashboard" && pendingApprovalCount > 0 && <b>{pendingApprovalCount}</b>}
            </button>
          ))}
        </nav>
        <button className="setup-card" onClick={() => setActiveTab("settings")}>
          <span><Zap size={15} /> 配置完成度 80%</span>
          <i><em /></i>
          <small>连接真实渠道即可 100%</small>
        </button>
        <div className="tenant">
          <span className="avatar">H</span>
          <div>
            <strong>Sunpath Outdoor</strong>
            <label htmlFor="seller">Seller</label>
          </div>
          <input id="seller" type="number" min="1" value={sellerId} onChange={(event) => setSellerId(Number(event.target.value || 1))} />
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div className="topbar-title">
            <h1>{activeNav.label}</h1>
            <p>{loading ? "同步中" : "本地 API 工作台"}</p>
          </div>
          <label className="global-search">
            <Search size={16} />
            <input placeholder="全局搜索 客户 / 询盘 / 产品" aria-label="全局搜索" />
          </label>
          <div className="top-tools">
            <IconButton label="刷新" onClick={loadAll} icon={RefreshCw} disabled={loading} />
            <span className="notification-dot">
              <IconButton label="审批" onClick={() => setActiveTab("approvals")} icon={ShieldCheck} />
              {pendingApprovalCount > 0 && <b>{pendingApprovalCount}</b>}
            </span>
            <IconButton label="语言与区域" icon={Globe2} />
            <span className="notification-dot">
              <IconButton label="通知" icon={Bell} />
              {unreadNotificationCount > 0 && <b>{unreadNotificationCount}</b>}
            </span>
            <span className="user-badge">H</span>
          </div>
        </header>

        {error && <div className="banner error">{error}</div>}
        {notice && <div className="banner ok">{notice}</div>}

        {activeTab === "dashboard" && (
          <Dashboard data={data} demo={demo} runWorkers={runWorkers} runDemoSeed={runDemoSeed} approveDemo={approveDemo} loading={loading} go={setActiveTab} />
        )}
        {activeTab === "inbox" && <Inbox inquiries={data.inquiries} messages={data.messages} demo={demo} />}
        {activeTab === "customers" && (
          <Customers
            customers={data.customers}
            selectedCustomer={selectedCustomer}
            quoteDetail={quoteDetail}
            openCustomer={openCustomer}
            openQuotation={openQuotation}
            sendQuotation={sendQuotation}
          />
        )}
        {activeTab === "products" && (
          <Products
            products={data.products}
            pricingRules={data.pricingRules}
            pricingVersions={data.pricingVersions}
            selectedPricingRuleId={data.selectedPricingRuleId}
            channels={data.channels}
            createProduct={createProduct}
            createPricingRule={createPricingRule}
            updatePricingRule={updatePricingRule}
            loadPricingVersions={loadPricingVersions}
            createChannel={createChannel}
            rotateChannel={rotateChannel}
          />
        )}
        {activeTab === "quoteRules" && <QuoteRulesPage pricingRules={data.pricingRules} />}
        {activeTab === "analytics" && <AnalyticsPage metrics={data.metrics} />}
        {activeTab === "mobile" && <MobilePreviewPage approvals={data.approvals} />}
        {activeTab === "approvals" && (
          <Approvals approvals={data.approvals} approveApproval={approveApproval} openQuotation={openQuotation} quoteDetail={quoteDetail} sendQuotation={sendQuotation} />
        )}
        {activeTab === "settings" && (
          <SettingsPanel
            readiness={data.readiness}
            notifications={data.notifications}
            settings={data.settings}
            saveSettings={saveSettings}
            markNotification={markNotification}
            runWorkers={runWorkers}
          />
        )}
      </main>
    </div>
  );
}

function Dashboard({ data, demo, runWorkers, runDemoSeed, approveDemo, loading, go }) {
  const metrics = data.metrics || {};
  const approval = metrics.approval || {};
  const delivery = metrics.delivery || {};
  const followup = metrics.followup || {};
  const pipeline = metrics.pipeline || {};
  const pendingApprovals = data.approvals?.items?.slice(0, 3) || [];
  const inquiryStream = data.inquiries?.items?.slice(0, 5) || [];
  return (
    <section className="dashboard-page">
      <div className="hero-row">
        <div>
          <h2>早上好，陈航</h2>
          <p>
            Closer 昨夜替你接住 {metrics.today_inquiries ?? pipeline.total ?? 0} 条询盘、自动报价 {metrics.quotation?.total ?? 0} 条。
            有 <strong>{approval.pending ?? 0} 条</strong>触发护栏，等你拍板。
          </p>
        </div>
        <div className="actions">
          <button className="primary" onClick={runDemoSeed} disabled={loading}>
            <Play size={17} />
            Demo Seed
          </button>
          <button onClick={approveDemo} disabled={loading}>
            <Check size={17} />
            审批发送
          </button>
          <button onClick={() => go("inbox")}>
            <InboxIcon size={17} />
            进入收件箱
          </button>
        </div>
      </div>

      <div className="metrics kpi-grid">
        <Metric label="今日新询盘" value={metrics.today_inquiries ?? pipeline.total ?? 0} tone="blue" delta="+3" />
        <Metric label="待我处理" value={metrics.pending_handoffs ?? approval.pending ?? 0} tone="amber" delta="转人工" />
        <Metric label="自动处理率" value={`${Math.round((metrics.auto_handle_rate || 0) * 100)}%`} tone="green" delta="+4pt" />
        <Metric label="本月成交转化" value={metrics.conversion ?? 0} tone="teal" delta="+2pt" />
      </div>

      <div className="dashboard-grid">
        <Panel
          title="待我处理"
          subtitle="护栏触发 / 大单 / 合同条款 — 需要你拍板"
          span="queue"
          action={<span className="badge badge-red">{approval.pending ?? pendingApprovals.length}</span>}
        >
          <Rows
            items={pendingApprovals}
            empty="暂无待处理动作。"
            render={(approvalItem) => (
              <div className="row-main">
                <span className="grade grade-a">A</span>
                <div>
                  <strong>{approvalItem.customer?.company || approvalItem.type}</strong>
                  <p>{approvalItem.summary || approvalItem.reason || "触发护栏，等待人工确认"}</p>
                </div>
                <small>{approvalItem.status}</small>
              </div>
            )}
          />
      </Panel>

        <Panel title="近 7 日" subtitle="询盘量 vs 成交" span="trend" action={<TrendingUp size={17} />}>
          <div className="trend-chart" aria-hidden="true">
            <i style={{ height: "45%" }} />
            <i style={{ height: "62%" }} />
            <i style={{ height: "42%" }} />
            <i style={{ height: "78%" }} />
            <i style={{ height: "55%" }} />
            <i style={{ height: "32%" }} />
            <i style={{ height: "70%" }} />
            <svg viewBox="0 0 240 80" preserveAspectRatio="none">
              <polyline points="0,58 40,50 80,60 120,44 160,52 200,66 240,43" />
            </svg>
          </div>
          <div className="legend"><span>询盘</span><span>成交</span></div>
        </Panel>
      </div>

      <Panel title="实时询盘流" subtitle="Agent 正在处理的最新动作" action={<span className="pill live"><span className="dot ready" />实时</span>}>
        <Rows
          items={inquiryStream}
          empty="暂无实时询盘。"
          render={(item) => (
            <div className="stream-row">
              <span>{item.received_at ? new Date(item.received_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "--:--"}</span>
              <strong>{item.customer?.company || item.customer?.email || `Inquiry #${item.id}`}</strong>
              <p>{item.summary || item.status}</p>
              <em>{item.status}</em>
            </div>
          )}
        />
      </Panel>

      <Panel title="Demo 控制台" subtitle="公开 API 演示链路" action={<Bot size={17} />}>
        <div className="stack">
          <button onClick={runWorkers}>
            <Send size={17} />
            Run Workers
          </button>
          {demo && <CodeBlock value={{ inquiry_id: demo.inquiry_id, conversation_id: demo.conversation_id, approval: demo.approval }} />}
        </div>
      </Panel>
    </section>
  );
}

function Inbox({ inquiries, messages, demo }) {
  return (
    <section className="split">
      <Panel title="高价值询盘" span="list">
        <Rows
          items={inquiries.items}
          empty="暂无询盘。"
          render={(item) => (
            <div className="row-main">
              <span className={`grade grade-${String(item.grade || "x").toLowerCase()}`}>{item.grade || "-"}</span>
              <div>
                <strong>{item.customer?.company || item.customer?.email || `Inquiry #${item.id}`}</strong>
                <p>{item.summary}</p>
              </div>
              <small>{item.status}</small>
            </div>
          )}
        />
      </Panel>
      <Panel title="当前会话消息" span="detail">
        <Rows
          items={messages.items}
          empty={demo ? "暂无新消息。" : "暂无会话消息。"}
          render={(message) => (
            <div className={`message ${message.sender_role}`}>
              <small>{message.sender_role}</small>
              <p>{message.content}</p>
            </div>
          )}
        />
      </Panel>
    </section>
  );
}

function Customers({ customers, selectedCustomer, quoteDetail, openCustomer, openQuotation, sendQuotation }) {
  return (
    <section className="split">
      <Panel title="客户列表" span="list">
        <Rows
          items={customers.items}
          empty="暂无客户。"
          render={(customer) => (
            <div className="row-main">
              <span className={`grade grade-${String(customer.grade || "x").toLowerCase()}`}>{customer.grade || "-"}</span>
              <div>
                <strong>{customer.company || customer.name || customer.email || `Customer #${customer.id}`}</strong>
                <p>{[customer.country, customer.email].filter(Boolean).join(" · ")}</p>
              </div>
              <button data-testid={`customer-${customer.id}-open`} onClick={() => openCustomer(customer.id)}>
                <Eye size={17} />
                查看
              </button>
            </div>
          )}
        />
      </Panel>
      <CustomerDetail customer={selectedCustomer} quoteDetail={quoteDetail} openQuotation={openQuotation} sendQuotation={sendQuotation} />
    </section>
  );
}

function CustomerDetail({ customer, quoteDetail, openQuotation, sendQuotation }) {
  if (!customer) {
    return (
      <Panel title="客户档案抽屉">
        <p className="empty">选择一个客户查看询盘、会话、报价与跟进。</p>
      </Panel>
    );
  }
  return (
    <div className="stack">
      <Panel title="客户档案抽屉">
        <div className="profile">
          <div>
            <span className={`grade grade-${String(customer.grade || "x").toLowerCase()}`}>{customer.grade || "-"}</span>
          </div>
          <div>
            <h3>{customer.company || customer.name || customer.email || `Customer #${customer.id}`}</h3>
            <p>{[customer.country, customer.email, customer.phone].filter(Boolean).join(" · ")}</p>
          </div>
        </div>
        <StatusRows
          rows={[
            ["状态", customer.status],
            ["询盘", customer.inquiries?.length || 0],
            ["会话", customer.conversations?.length || 0],
            ["报价", customer.quotations?.length || 0],
            ["跟进", customer.followups?.length || 0],
          ]}
        />
      </Panel>
      <Panel title="客户活动">
        <ActivityGroup title="询盘" items={customer.inquiries} render={(item) => `${item.grade || "-"} · ${item.status} · ${item.summary || item.id}`} />
        <ActivityGroup title="会话" items={customer.conversations} render={(item) => `${item.channel} · ${item.status} · #${item.id}`} />
        <ActivityGroup
          title="报价"
          items={customer.quotations}
          render={(item) => `${item.currency} ${item.total_amount ?? "-"} · ${item.status}`}
          action={(item) => (
            <button data-testid={`quotation-${item.id}-open`} onClick={() => openQuotation(item.id)}>
              <Eye size={17} />
              详情
            </button>
          )}
        />
        <ActivityGroup title="跟进" items={customer.followups} render={(item) => `${item.status} · ${item.next_run_at || item.stop_reason || "-"}`} />
      </Panel>
      <QuotationDetail quote={quoteDetail} sendQuotation={sendQuotation} />
    </div>
  );
}

function ActivityGroup({ title, items = [], render, action }) {
  return (
    <div className="activity">
      <h3>{title}</h3>
      {items.length ? (
        items.map((item) => (
          <div className="activity-row" key={`${title}-${item.id}`}>
            <span>{render(item)}</span>
            {action?.(item)}
          </div>
        ))
      ) : (
        <p className="empty">暂无{title}</p>
      )}
    </div>
  );
}

function QuotationDetail({ quote, sendQuotation }) {
  if (!quote) {
    return (
      <Panel title="报价详情">
        <p className="empty">选择客户报价查看明细。</p>
      </Panel>
    );
  }
  return (
    <Panel title={`报价详情 #${quote.id}`}>
      <StatusRows
        rows={[
          ["状态", quote.status],
          ["总额", `${quote.currency} ${quote.total_amount ?? "-"}`],
          ["有效期", quote.valid_until || "-"],
          ["命中底价", quote.hits_floor ? "yes" : "no"],
        ]}
      />
      <div className="quote-lines">
        {(quote.items || []).map((item) => (
          <div key={item.id || item.product_id}>
            <span>Product #{item.product_id}</span>
            <strong>{item.quantity} x {quote.currency} {item.unit_price}</strong>
            <small>{quote.currency} {item.amount}</small>
          </div>
        ))}
      </div>
      {quote.terms?.message && <p className="quote-message">{quote.terms.message}</p>}
      <button data-testid={`quotation-${quote.id}-send`} onClick={() => sendQuotation(quote.id)}>
        <Send size={17} />
        发送报价
      </button>
    </Panel>
  );
}

function Approvals({ approvals, approveApproval, openQuotation, quoteDetail, sendQuotation }) {
  return (
    <section className="split">
      <Panel title="人工审批队列">
        <Rows
          items={approvals.items}
          empty="暂无待审批动作。"
          render={(approval) => (
            <div className="approval-row">
              <div>
                <strong>{approval.type}</strong>
                <p>{approval.summary || approval.reason}</p>
              </div>
              <div className="inline-actions">
                {approval.payload?.quotation_id && (
                  <button data-testid={`approval-${approval.id}-quotation`} onClick={() => openQuotation(approval.payload.quotation_id)}>
                    <Eye size={17} />
                    报价
                  </button>
                )}
                <button data-testid={`approval-${approval.id}-approve`} onClick={() => approveApproval(approval.id)}>
                  <Check size={17} />
                  批准
                </button>
              </div>
            </div>
          )}
        />
      </Panel>
      <QuotationDetail quote={quoteDetail} sendQuotation={sendQuotation} />
    </section>
  );
}

function SettingsPanel({ readiness, notifications, settings, saveSettings, markNotification, runWorkers }) {
  const checks = readiness.checks || [];
  return (
    <section className="split">
      <Panel title="生产就绪">
        <Rows
          items={checks}
          empty="暂无 readiness 数据。"
          render={(check) => (
            <div className="row-main">
              <span className={`dot ${check.status}`}></span>
              <div>
                <strong>{check.name}</strong>
                <p>{check.message}</p>
              </div>
              <small>{check.status}</small>
            </div>
          )}
        />
      </Panel>
      <Panel title="通知与调度">
        <Rows
          items={notifications.items}
          empty="暂无未读通知。"
          render={(item) => (
            <div className="approval-row">
              <div>
                <strong>{item.title}</strong>
                <p>{item.body || item.severity}</p>
              </div>
              <div className="inline-actions">
                <button data-testid={`notification-${item.id}-read`} onClick={() => markNotification(item.id, "read")}>
                  <Check size={17} />
                  已读
                </button>
                <button data-testid={`notification-${item.id}-archive`} onClick={() => markNotification(item.id, "archived")}>
                  <Archive size={17} />
                  归档
                </button>
              </div>
            </div>
          )}
        />
        <button onClick={runWorkers}>
          <Send size={17} />
          运行调度入口
        </button>
      </Panel>
      <Panel title="卖家设置" span="list">
        <ApiForm testId="settings-form" onSubmit={saveSettings} submitLabel="保存设置" key={settings?.id || "empty"}>
          <Field name="name" label="名称" defaultValue={settings?.name || "Demo Exporter"} required />
          <div className="form-grid">
            <Field name="phone" label="电话" defaultValue={settings?.phone || ""} />
            <Field name="plan" label="方案" defaultValue={settings?.plan || "mvp"} required />
            <Field
              name="large_order_approval_threshold"
              label="大额阈值"
              type="number"
              defaultValue={settings?.settings?.large_order_approval_threshold || "10000"}
            />
          </div>
          <label className="check-field">
            <input name="ai_disclosure" type="checkbox" defaultChecked={settings?.ai_disclosure !== false} />
            <span>AI disclosure</span>
          </label>
        </ApiForm>
      </Panel>
    </section>
  );
}
