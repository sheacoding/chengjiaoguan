/**
 * [INPUT]: 依赖 lucide-react 图标、frontend/src/ui.jsx 基元与离线设计稿的产品库工具栏结构
 * [OUTPUT]: 对外提供 Products 组件，承载设计稿对齐的产品库标题、搜索工具、价格规则编辑/版本与渠道凭据轮换 UI
 * [POS]: frontend/src 的产品配置域，从 App.jsx 拆出产品/价格/渠道交互，避免页面组合根膨胀
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

import { Eye, RefreshCw, Search, Upload } from "lucide-react";
import { ApiForm, Field, JsonField, Panel, Rows } from "./ui.jsx";

export function Products({
  products,
  pricingRules,
  pricingVersions,
  selectedPricingRuleId,
  channels,
  createProduct,
  createPricingRule,
  updatePricingRule,
  loadPricingVersions,
  createChannel,
  rotateChannel,
}) {
  return (
    <section className="product-page">
      <div className="page-heading">
        <div>
          <h2>产品库</h2>
          <p>{products.total ?? products.items?.length ?? 0} 个 SKU · 支撑需求理解与自动报价的知识底座</p>
        </div>
        <div className="page-tools">
          <label className="local-search">
            <Search size={16} />
            <input placeholder="搜索产品 / SKU / 品类" aria-label="搜索产品" />
          </label>
          <button><Upload size={16} />Excel 批量导入</button>
        </div>
      </div>
      <div className="split">
        <div className="stack">
        <Panel title="产品库" span="list">
          <Rows
            items={products.items}
            empty="暂无产品。"
            render={(product) => (
              <div className="row-main">
                <span className="sku">{product.sku || product.id}</span>
                <div>
                  <strong>{product.name}</strong>
                  <p>{product.currency} {product.cost ?? "-"} · MOQ {product.moq ?? "-"}</p>
                </div>
                <small>{product.status}</small>
              </div>
            )}
          />
        </Panel>
        <PricingRules pricingRules={pricingRules} updatePricingRule={updatePricingRule} loadPricingVersions={loadPricingVersions} />
      </div>
      <div className="stack">
        <Panel title="新增产品">
          <ApiForm testId="product-form" onSubmit={createProduct} submitLabel="创建产品">
            <Field name="name" label="名称" required defaultValue="LED Desk Lamp" />
            <Field name="sku" label="SKU" defaultValue="LAMP-10W" />
            <div className="form-grid">
              <Field name="cost" label="成本" type="number" step="0.01" defaultValue="2.00" />
              <Field name="moq" label="MOQ" type="number" defaultValue="100" />
              <Field name="currency" label="币种" defaultValue="USD" />
            </div>
            <Field name="description" label="描述" defaultValue="Aluminum desk lamp." />
            <JsonField name="specs" label="规格 JSON" defaultValue={{ power: "10W" }} />
          </ApiForm>
        </Panel>
        <Panel title="新建价格规则">
          <ApiForm testId="pricing-form" onSubmit={createPricingRule} submitLabel="创建规则">
            <Field name="product_id" label="产品 ID" type="number" defaultValue={products.items[0]?.id || ""} required />
            <div className="form-grid">
              <Field name="margin_rate" label="利润率" type="number" step="0.01" defaultValue="0.25" />
              <Field name="floor_price" label="底价" type="number" step="0.01" defaultValue="3.00" required />
              <Field name="currency" label="币种" defaultValue="USD" />
            </div>
            <Field name="valid_days" label="有效天数" type="number" defaultValue="14" />
            <JsonField name="logistics_template" label="物流 JSON" defaultValue={{ unit_cost: "0.10" }} />
            <JsonField name="tiered_prices" label="阶梯价 JSON" defaultValue={[{ min_qty: 500, price: "3.20" }]} />
          </ApiForm>
        </Panel>
        <PricingVersions versions={pricingVersions} selectedPricingRuleId={selectedPricingRuleId} />
        <Panel title="渠道">
          <Rows
            items={channels.items}
            empty="暂无渠道配置。"
            render={(channel) => (
              <div className="approval-row">
                <div>
                  <strong>{channel.channel_type}</strong>
                  <p>{channel.status} · key {channel.credentials_key_status}</p>
                </div>
                <button data-testid={`channel-${channel.id}-rotate`} onClick={() => rotateChannel(channel.id)}>
                  <RefreshCw size={17} />
                  轮换
                </button>
              </div>
            )}
          />
          <ApiForm testId="channel-form" onSubmit={createChannel} submitLabel="创建渠道">
            <label className="field">
              <span>类型</span>
              <select name="channel_type" defaultValue="email">
                <option value="site_form">site_form</option>
                <option value="email">email</option>
                <option value="whatsapp">whatsapp</option>
              </select>
            </label>
            <Field name="name" label="名称" defaultValue="Sales inbox" />
            <JsonField name="credentials" label="凭据 JSON" defaultValue={{ host: "imap.example.com" }} />
          </ApiForm>
        </Panel>
      </div>
      </div>
    </section>
  );
}

function PricingRules({ pricingRules, updatePricingRule, loadPricingVersions }) {
  return (
    <Panel title="价格规则列表">
      <Rows
        items={pricingRules.items}
        empty="暂无价格规则。"
        render={(rule) => (
          <div className="stack">
            <div className="approval-row">
              <div>
                <strong>Rule #{rule.id} · Product #{rule.product_id || "-"}</strong>
                <p>{rule.currency} floor {rule.floor_price} · margin {rule.margin_rate ?? "-"}</p>
              </div>
              <button data-testid={`pricing-rule-${rule.id}-versions`} onClick={() => loadPricingVersions(rule.id)}>
                <Eye size={17} />
                版本
              </button>
            </div>
            <ApiForm testId={`pricing-rule-${rule.id}-edit`} onSubmit={(form) => updatePricingRule(rule.id, form)} submitLabel="更新规则">
              <div className="form-grid">
                <Field name="product_id" label="产品 ID" type="number" defaultValue={rule.product_id || ""} />
                <Field name="margin_rate" label="利润率" type="number" step="0.01" defaultValue={rule.margin_rate ?? ""} />
                <Field name="floor_price" label="底价" type="number" step="0.01" defaultValue={rule.floor_price ?? ""} />
                <Field name="currency" label="币种" defaultValue={rule.currency || "USD"} />
                <Field name="valid_days" label="有效天数" type="number" defaultValue={rule.valid_days || ""} />
              </div>
              <JsonField name="logistics_template" label="物流 JSON" defaultValue={rule.logistics_template || {}} />
              <JsonField name="tiered_prices" label="阶梯价 JSON" defaultValue={rule.tiered_prices || []} />
            </ApiForm>
          </div>
        )}
      />
    </Panel>
  );
}

function PricingVersions({ versions, selectedPricingRuleId }) {
  return (
    <Panel title="版本历史">
      {!selectedPricingRuleId ? (
        <p className="empty">选择价格规则查看版本。</p>
      ) : (
        <Rows
          items={versions?.items}
          empty="暂无版本记录。"
          render={(version) => (
            <div className="row-main">
              <span className="sku">v{version.version}</span>
              <div>
                <strong>{version.action_type}</strong>
                <p>floor {version.snapshot?.floor_price ?? "-"} · currency {version.snapshot?.currency ?? "-"}</p>
              </div>
              <small>{version.actor}</small>
            </div>
          )}
        />
      )}
    </Panel>
  );
}
