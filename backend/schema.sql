-- Run this in Supabase SQL Editor

CREATE TABLE leads (
  id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  channel         TEXT NOT NULL CHECK (channel IN ('whatsapp','whatsapp_dev','email','instagram')),
  sender_id       TEXT NOT NULL,
  sender_name     TEXT,
  stage           TEXT NOT NULL DEFAULT 'NEW'
                    CHECK (stage IN ('NEW','GATHERING','QUALIFYING','QUALIFIED',
                                     'SCHEDULING','BOOKED','NOT_QUALIFIED','HUMAN_TAKEOVER')),
  qualified       BOOLEAN,
  assigned_rep    TEXT CHECK (assigned_rep IN ('Arjun','Priya')),
  evidence_json   JSONB DEFAULT '{}',
  human_takeover  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (channel, sender_id)
);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$;

CREATE TRIGGER leads_updated_at
  BEFORE UPDATE ON leads
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE messages (
  id         UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  lead_id    UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  role       TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content    TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_messages_lead_id ON messages(lead_id);

CREATE TABLE bookings (
  id                 UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  lead_id            UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  rep                TEXT NOT NULL,
  slot_start         TIMESTAMPTZ NOT NULL,
  slot_end           TIMESTAMPTZ NOT NULL,
  calendar_event_id  TEXT,
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (lead_id, slot_start)
);

CREATE TABLE action_log (
  id         UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  lead_id    UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  event      TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_action_log_lead_id ON action_log(lead_id);

ALTER PUBLICATION supabase_realtime ADD TABLE leads;
ALTER PUBLICATION supabase_realtime ADD TABLE messages;
ALTER PUBLICATION supabase_realtime ADD TABLE bookings;
ALTER PUBLICATION supabase_realtime ADD TABLE action_log;

ALTER TABLE leads      ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages   ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings   ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "auth users full access" ON leads
  FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "auth users full access" ON messages
  FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "auth users full access" ON bookings
  FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "auth users full access" ON action_log
  FOR ALL TO authenticated USING (true) WITH CHECK (true);
