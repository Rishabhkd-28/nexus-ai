/**
 * EmailPanel.jsx
 * Shows all email leads with their full inbound + outbound thread.
 * Fully separate view in the dashboard — not mixed with WhatsApp leads.
 */
import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import { format, formatDistanceToNow } from "date-fns";

const STAGE_COLORS = {
  NEW:            "bg-gray-100 text-gray-700",
  GATHERING:      "bg-blue-100 text-blue-700",
  QUALIFYING:     "bg-yellow-100 text-yellow-700",
  QUALIFIED:      "bg-green-100 text-green-700",
  SCHEDULING:     "bg-purple-100 text-purple-700",
  BOOKED:         "bg-emerald-100 text-emerald-700",
  NOT_QUALIFIED:  "bg-red-100 text-red-700",
  HUMAN_TAKEOVER: "bg-orange-100 text-orange-700",
};

export default function EmailPanel() {
  const [leads, setLeads]       = useState([]);
  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);

  // Fetch email leads
  useEffect(() => {
    fetchLeads();
    const ch = supabase
      .channel("email-leads-realtime")
      .on("postgres_changes", { event: "*", schema: "public", table: "leads" }, fetchLeads)
      .subscribe();
    return () => supabase.removeChannel(ch);
  }, []);

  // Fetch messages when lead selected
  useEffect(() => {
    if (!selected) return;
    setMessages([]);
    fetchMessages(selected.id);

    const ch = supabase
      .channel(`email-msgs-${selected.id}`)
      .on("postgres_changes", {
        event: "INSERT",
        schema: "public",
        table: "messages",
        filter: `lead_id=eq.${selected.id}`,
      }, (payload) => setMessages((prev) => [...prev, payload.new]))
      .subscribe();

    return () => supabase.removeChannel(ch);
  }, [selected?.id]);

  async function fetchLeads() {
    const { data } = await supabase
      .from("leads")
      .select("*")
      .eq("channel", "email")
      .order("updated_at", { ascending: false });
    if (data) setLeads(data);
  }

  async function fetchMessages(leadId) {
    const { data } = await supabase
      .from("messages")
      .select("*")
      .eq("lead_id", leadId)
      .order("created_at");
    if (data) setMessages(data);
  }

  async function handleTakeover(leadId, current) {
    await supabase.from("leads")
      .update({ human_takeover: !current, stage: current ? "QUALIFYING" : "HUMAN_TAKEOVER" })
      .eq("id", leadId);
    setSelected((s) => s ? { ...s, human_takeover: !current } : s);
  }

  // Parse display name and subject from sender_name field
  function parseEmailMeta(lead) {
    const parts = (lead.sender_name || "").split(" | ");
    return {
      from:    parts[0] || lead.sender_id,
      subject: parts[1] || "(no subject)",
    };
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-5 gap-6 h-full">

      {/* Left: lead list */}
      <div className="xl:col-span-2 bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden flex flex-col">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">📧 Email Leads</h2>
          <span className="text-xs text-gray-400">{leads.length} threads</span>
        </div>

        <div className="divide-y divide-gray-50 overflow-y-auto flex-1">
          {leads.map((lead) => {
            const { from, subject } = parseEmailMeta(lead);
            const isSelected = selected?.id === lead.id;
            return (
              <div
                key={lead.id}
                onClick={() => setSelected(lead)}
                className={`px-5 py-4 cursor-pointer hover:bg-gray-50 transition-colors ${
                  isSelected ? "bg-indigo-50 border-l-2 border-indigo-500" : ""
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-gray-900 truncate text-sm">{from}</p>
                    <p className="text-xs text-gray-500 truncate mt-0.5">{subject}</p>
                    <p className="text-xs text-gray-400 mt-1">
                      {formatDistanceToNow(new Date(lead.updated_at || lead.created_at), { addSuffix: true })}
                    </p>
                  </div>
                  <span className={`flex-shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${
                    STAGE_COLORS[lead.stage] || "bg-gray-100 text-gray-600"
                  }`}>
                    {lead.stage}
                  </span>
                </div>
              </div>
            );
          })}
          {leads.length === 0 && (
            <div className="px-5 py-10 text-center text-gray-400 text-sm">
              No email leads yet.<br />
              <span className="text-xs">Emails to your Gmail inbox are polled every 60s.</span>
            </div>
          )}
        </div>
      </div>

      {/* Right: thread view */}
      <div className="xl:col-span-3 bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col min-h-[500px]">
        {!selected ? (
          <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
            Select an email thread to view the conversation
          </div>
        ) : (
          <>
            {/* Thread header */}
            <div className="px-6 py-4 border-b border-gray-100">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <h3 className="font-semibold text-gray-900 truncate">
                    {parseEmailMeta(selected).subject}
                  </h3>
                  <p className="text-xs text-gray-500 mt-0.5">
                    From: {parseEmailMeta(selected).from}
                    {" · "}{selected.sender_id}
                  </p>
                  {selected.assigned_rep && (
                    <p className="text-xs text-gray-500 mt-0.5">
                      Assigned to: <span className="font-medium">{selected.assigned_rep}</span>
                    </p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-2 flex-shrink-0">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    STAGE_COLORS[selected.stage] || "bg-gray-100 text-gray-600"
                  }`}>
                    {selected.stage}
                  </span>
                  <button
                    onClick={() => handleTakeover(selected.id, selected.human_takeover)}
                    className={`text-xs px-2 py-1 rounded transition-colors ${
                      selected.human_takeover
                        ? "bg-green-100 text-green-700 hover:bg-green-200"
                        : "bg-orange-100 text-orange-700 hover:bg-orange-200"
                    }`}
                  >
                    {selected.human_takeover ? "Release to AI" : "Take Over"}
                  </button>
                </div>
              </div>

              {/* Evidence */}
              {selected.evidence_json && Object.keys(selected.evidence_json).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {Object.entries(selected.evidence_json).map(([k, v]) =>
                    v !== null && v !== undefined && k !== "disqualifiers" ? (
                      <span key={k} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                        {k}: <span className="font-medium">{String(v)}</span>
                      </span>
                    ) : null
                  )}
                </div>
              )}
            </div>

            {/* Messages — styled as email thread */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
              {messages.map((msg) => (
                <div key={msg.id} className={`${
                  msg.role === "user"
                    ? "border-l-2 border-gray-300 pl-4"
                    : "border-l-2 border-indigo-400 pl-4"
                }`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-semibold ${
                      msg.role === "user" ? "text-gray-700" : "text-indigo-700"
                    }`}>
                      {msg.role === "user" ? "📨 Inbound" : "📤 Bot reply"}
                    </span>
                    <span className="text-xs text-gray-400">
                      {format(new Date(msg.created_at), "d MMM, HH:mm")}
                    </span>
                  </div>
                  <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
                    {msg.content}
                  </p>
                </div>
              ))}
              {messages.length === 0 && (
                <p className="text-sm text-gray-400 text-center py-8">No messages yet</p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
