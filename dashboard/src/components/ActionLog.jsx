import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import { formatDistanceToNow } from "date-fns";

const EVENT_ICON = {
  "lead created":    "🆕",
  qualified:         "✅",
  "not qualified":   "❌",
  "booking created": "📅",
  takeover:          "👤",
};

function iconFor(event) {
  for (const [key, icon] of Object.entries(EVENT_ICON)) {
    if (event.toLowerCase().includes(key)) return icon;
  }
  return "📌";
}

export default function ActionLog({ leadId }) {
  const [events, setEvents] = useState([]);

  useEffect(() => {
    if (!leadId) {
      fetchAll();
      return;
    }
    fetchForLead(leadId);

    const ch = supabase
      .channel(`log-${leadId || "all"}`)
      .on("postgres_changes", {
        event: "INSERT",
        schema: "public",
        table: "action_log",
      }, () => {
        leadId ? fetchForLead(leadId) : fetchAll();
      })
      .subscribe();

    return () => supabase.removeChannel(ch);
  }, [leadId]);

  async function fetchAll() {
    const { data } = await supabase
      .from("action_log")
      .select("*, leads(sender_name, sender_id)")
      .order("created_at", { ascending: false })
      .limit(50);
    if (data) setEvents(data);
  }

  async function fetchForLead(id) {
    const { data } = await supabase
      .from("action_log")
      .select("*")
      .eq("lead_id", id)
      .order("created_at", { ascending: false });
    if (data) setEvents(data);
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100">
        <h2 className="font-semibold text-gray-900">
          {leadId ? "Lead Events" : "All Activity"}
        </h2>
      </div>

      <div className="divide-y divide-gray-50 max-h-[400px] overflow-y-auto">
        {events.map((e) => (
          <div key={e.id} className="px-6 py-3 flex items-start gap-3">
            <span className="text-lg flex-shrink-0">{iconFor(e.event)}</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-800">{e.event}</p>
              {e.leads && (
                <p className="text-xs text-gray-400 truncate">
                  {e.leads.sender_name || e.leads.sender_id}
                </p>
              )}
            </div>
            <span className="text-xs text-gray-400 flex-shrink-0 mt-0.5">
              {formatDistanceToNow(new Date(e.created_at), { addSuffix: true })}
            </span>
          </div>
        ))}
        {events.length === 0 && (
          <div className="px-6 py-8 text-center text-gray-400 text-sm">
            No activity yet
          </div>
        )}
      </div>
    </div>
  );
}
