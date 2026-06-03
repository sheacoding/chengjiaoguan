/**
 * [INPUT]: 依赖浏览器 FormData
 * [OUTPUT]: 对外提供 safeGet、productPayload、pricingPayload、channelPayload、settingsPayload
 * [POS]: frontend/src 的表单归一层，把 UI 表单值折叠成后端 schema 接受的最小 payload
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

export async function safeGet(api, path, fallback) {
  try {
    return await api.get(path);
  } catch {
    return fallback;
  }
}

export function productPayload(form) {
  return compact({
    name: text(form, "name"),
    sku: text(form, "sku"),
    cost: text(form, "cost"),
    currency: text(form, "currency") || "USD",
    moq: numberValue(form, "moq"),
    description: text(form, "description"),
    specs: jsonValue(form, "specs", {}),
  });
}

export function pricingPayload(form) {
  return compact({
    product_id: numberValue(form, "product_id"),
    margin_rate: text(form, "margin_rate"),
    logistics_template: jsonValue(form, "logistics_template", {}),
    tiered_prices: jsonValue(form, "tiered_prices", []),
    valid_days: numberValue(form, "valid_days"),
    floor_price: text(form, "floor_price"),
    currency: text(form, "currency") || "USD",
  });
}

export function channelPayload(form) {
  return compact({
    channel_type: text(form, "channel_type"),
    name: text(form, "name"),
    credentials: jsonValue(form, "credentials", {}),
    status: "connected",
  });
}

export function settingsPayload(form) {
  return compact({
    name: text(form, "name"),
    phone: text(form, "phone"),
    plan: text(form, "plan"),
    ai_disclosure: form.get("ai_disclosure") === "on",
    settings: compact({
      large_order_approval_threshold: text(form, "large_order_approval_threshold"),
    }),
  });
}

function jsonValue(form, name, fallback) {
  const raw = text(form, name);
  if (!raw) return fallback;
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw new Error(`${name} JSON 无效: ${error.message}`);
  }
}

function text(form, name) {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function numberValue(form, name) {
  const value = text(form, name);
  return value ? Number(value) : undefined;
}

function compact(value) {
  return Object.fromEntries(Object.entries(value).filter(([, entry]) => entry !== "" && entry !== undefined && entry !== null));
}
