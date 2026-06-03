CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE seller (
  id BIGSERIAL PRIMARY KEY,
  name varchar(120) NOT NULL,
  email varchar(160) UNIQUE NOT NULL,
  phone varchar(40),
  plan varchar(20) NOT NULL DEFAULT 'free',
  ai_disclosure boolean NOT NULL DEFAULT true,
  settings jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE seller_api_key (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  name varchar(120) NOT NULL,
  token_prefix varchar(24) NOT NULL,
  token_hash varchar(64) NOT NULL,
  scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
  status varchar(20) NOT NULL DEFAULT 'active',
  last_used_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_seller_api_key_token_hash UNIQUE (token_hash)
);

CREATE TABLE channel_account (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  channel_type varchar(20) NOT NULL,
  name varchar(120),
  credentials jsonb NOT NULL DEFAULT '{}'::jsonb,
  status varchar(20) NOT NULL DEFAULT 'connected',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE product (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  name varchar(200) NOT NULL,
  sku varchar(80),
  specs jsonb NOT NULL DEFAULT '{}'::jsonb,
  cost numeric(14,2),
  currency varchar(8) NOT NULL DEFAULT 'USD',
  moq integer,
  images jsonb NOT NULL DEFAULT '[]'::jsonb,
  description text,
  status varchar(20) NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE pricing_rule (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  product_id bigint REFERENCES product(id),
  margin_rate numeric(6,4),
  logistics_template jsonb NOT NULL DEFAULT '{}'::jsonb,
  exchange_source varchar(40),
  tiered_prices jsonb NOT NULL DEFAULT '[]'::jsonb,
  valid_days integer,
  floor_price numeric(14,2) NOT NULL,
  currency varchar(8) NOT NULL DEFAULT 'USD',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE pricing_rule_version (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  pricing_rule_id bigint NOT NULL REFERENCES pricing_rule(id),
  version integer NOT NULL,
  actor varchar(12),
  action_type varchar(40) NOT NULL,
  snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_pricing_rule_version_rule_version UNIQUE (pricing_rule_id, version)
);

CREATE TABLE customer (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  name varchar(160),
  company varchar(200),
  country varchar(80),
  email varchar(160),
  phone varchar(40),
  channels jsonb NOT NULL DEFAULT '{}'::jsonb,
  grade char(1),
  enrichment jsonb NOT NULL DEFAULT '{}'::jsonb,
  preferences jsonb NOT NULL DEFAULT '{}'::jsonb,
  status varchar(20) NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE inquiry (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  customer_id bigint NOT NULL REFERENCES customer(id),
  channel_account_id bigint REFERENCES channel_account(id),
  source_channel varchar(20),
  raw_content text,
  parsed jsonb NOT NULL DEFAULT '{}'::jsonb,
  grade char(1),
  score numeric(5,2),
  status varchar(20) NOT NULL DEFAULT 'new',
  language varchar(12),
  received_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE conversation (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  customer_id bigint NOT NULL REFERENCES customer(id),
  inquiry_id bigint NOT NULL REFERENCES inquiry(id),
  channel varchar(20),
  language varchar(12),
  is_human_takeover boolean NOT NULL DEFAULT false,
  status varchar(20) NOT NULL DEFAULT 'open',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE message (
  id BIGSERIAL PRIMARY KEY,
  conversation_id bigint NOT NULL REFERENCES conversation(id),
  sender_role varchar(12) NOT NULL,
  channel_message_id varchar(120) UNIQUE,
  content text,
  attachments jsonb NOT NULL DEFAULT '[]'::jsonb,
  language varchar(12),
  sent_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE delivery_attempt (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  message_id bigint NOT NULL REFERENCES message(id),
  channel_account_id bigint REFERENCES channel_account(id),
  channel varchar(20) NOT NULL,
  external_id varchar(120) NOT NULL,
  status varchar(20) NOT NULL,
  client varchar(40),
  provider_message_id varchar(120),
  attempt_count integer NOT NULL DEFAULT 1,
  next_retry_at timestamptz,
  error text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  response jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE quotation (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  inquiry_id bigint NOT NULL REFERENCES inquiry(id),
  customer_id bigint NOT NULL REFERENCES customer(id),
  currency varchar(8) NOT NULL DEFAULT 'USD',
  total_amount numeric(14,2),
  terms jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_until date,
  is_pi boolean NOT NULL DEFAULT false,
  status varchar(20) NOT NULL DEFAULT 'draft',
  created_by varchar(8),
  hits_floor boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE quotation_item (
  id BIGSERIAL PRIMARY KEY,
  quotation_id bigint NOT NULL REFERENCES quotation(id),
  product_id bigint NOT NULL REFERENCES product(id),
  quantity integer NOT NULL,
  unit_price numeric(14,2) NOT NULL,
  amount numeric(14,2) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE followup_task (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  inquiry_id bigint NOT NULL REFERENCES inquiry(id),
  conversation_id bigint NOT NULL REFERENCES conversation(id),
  schedule jsonb NOT NULL DEFAULT '{}'::jsonb,
  next_run_at timestamptz,
  status varchar(20) NOT NULL DEFAULT 'active',
  stop_reason varchar(40),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE knowledge_chunk (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  source_type varchar(20),
  source_ref varchar(120),
  content text NOT NULL,
  embedding vector(1536),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE notification (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  type varchar(40) NOT NULL,
  severity varchar(20) NOT NULL DEFAULT 'info',
  title varchar(160) NOT NULL,
  body text,
  target_type varchar(40),
  target_id bigint,
  context jsonb NOT NULL DEFAULT '{}'::jsonb,
  status varchar(20) NOT NULL DEFAULT 'unread',
  read_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  actor varchar(12),
  action_type varchar(40),
  target_type varchar(40),
  target_id bigint,
  is_auto boolean,
  snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE approval (
  id BIGSERIAL PRIMARY KEY,
  seller_id bigint NOT NULL REFERENCES seller(id),
  conversation_id bigint NOT NULL REFERENCES conversation(id),
  inquiry_id bigint NOT NULL REFERENCES inquiry(id),
  type varchar(40) NOT NULL,
  reason varchar(80) NOT NULL,
  summary text NOT NULL,
  suggestion text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status varchar(20) NOT NULL DEFAULT 'pending',
  executed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_channel_account_seller_id ON channel_account(seller_id);
CREATE INDEX ix_seller_api_key_seller_status ON seller_api_key(seller_id, status);
CREATE INDEX ix_product_seller_id ON product(seller_id);
CREATE INDEX ix_pricing_rule_seller_id ON pricing_rule(seller_id);
CREATE INDEX ix_pricing_rule_version_rule_id ON pricing_rule_version(pricing_rule_id);
CREATE INDEX ix_pricing_rule_version_seller_id ON pricing_rule_version(seller_id);
CREATE INDEX ix_customer_seller_email ON customer(seller_id, email);
CREATE INDEX ix_customer_seller_grade ON customer(seller_id, grade);
CREATE INDEX ix_inquiry_seller_status ON inquiry(seller_id, status);
CREATE INDEX ix_inquiry_seller_grade ON inquiry(seller_id, grade);
CREATE INDEX ix_inquiry_customer_id ON inquiry(customer_id);
CREATE INDEX ix_conversation_seller_id ON conversation(seller_id);
CREATE INDEX ix_message_conversation_sent_at ON message(conversation_id, sent_at);
CREATE INDEX ix_delivery_attempt_seller_status ON delivery_attempt(seller_id, status);
CREATE INDEX ix_delivery_attempt_next_retry ON delivery_attempt(next_retry_at, status);
CREATE INDEX ix_delivery_attempt_message_id ON delivery_attempt(message_id);
CREATE INDEX ix_quotation_inquiry_id ON quotation(inquiry_id);
CREATE INDEX ix_quotation_seller_status ON quotation(seller_id, status);
CREATE INDEX ix_quotation_item_quotation_id ON quotation_item(quotation_id);
CREATE INDEX ix_followup_next_status ON followup_task(next_run_at, status);
CREATE INDEX ix_knowledge_chunk_seller_id ON knowledge_chunk(seller_id);
CREATE INDEX ix_knowledge_chunk_embedding ON knowledge_chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ix_notification_seller_status ON notification(seller_id, status);
CREATE INDEX ix_notification_target ON notification(target_type, target_id);
CREATE INDEX ix_audit_log_seller_created_at ON audit_log(seller_id, created_at);
CREATE INDEX ix_approval_seller_status ON approval(seller_id, status);
CREATE INDEX ix_approval_conversation_id ON approval(conversation_id);
