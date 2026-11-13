import { useEffect, useRef, useState } from "react";
import { supabase } from "../lib/supabase";
import { format } from "date-fns";

const CHANNEL_LABEL = {
  whatsapp:  "WhatsApp",
  email:     "Email",
  instagram: "Instagram",
};

export default function ConversationPanel({ lead }) {
  const [messages, setMessages] = useState([]);
  const bottomRef = useRef(null);

  useEffect(() => {
    if (!lead) return;
    setMessages([]);
    fetchMessages(lead.id);

    const ch = supabase
      .channel(`msgs-${lead.id}`)
      .on("postgres_changes", {
        event: "INSERT",
        schema: "public",
        table: "messages",
        filter: `lead_id=eq.${lead.id}`,
      }, (payload) => {
        setMessages((prev) => [...prev, payload.new]);
      })
      .subscribe();

    return () => supabase.removeChannel(ch);
  }, [lead?.id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function fetchMessages(leadId) {
    const { data } = await supabase
      .from("messages")
      .select("*")
      .eq("lead_id", leadId)
      .order("created_at");
    if (data) setMessages(data);
  }

  if (!lead) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 flex items-center justify-center h-full min-h-[400px]">
        <p className="text-gray-400 text-sm">Select a lead to view the conversation</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col h-full min-h-[400px]">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-100">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-gray-900">
              {lead.sender_name || lead.sender_id}
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">
              {CHANNEL_LABEL[lead.channel]} · {lead.stage}
              {lead.assigned_rep && ` · ${lead.assigned_rep}`}
            </p>
          </div>
          {lead.human_takeover && (
            <span className="text-xs bg-orange-100 text-orange-700 px-2 py-1 rounded-full font-medium">
              Human Takeover Active
            </span>
          )}
        </div>

        {/* Evidence pills */}
        {lead.evidence_json && Object.keys(lead.evidence_json).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(lead.evidence_json).map(([k, v]) =>
              v !== null && v !== undefined && k !== "disqualifiers" ? (
                <span
                  key={k}
                  className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded"
                >
                  {k}: <span className="font-medium">{String(v)}</span>
                </span>
              ) : null
            )}
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-start" : "justify-end"}`}
          >
            <div
              className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm ${
                msg.role === "user"
                  ? "bg-gray-100 text-gray-900 rounded-tl-sm"
                  : "bg-indigo-600 text-white rounded-tr-sm"
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
              <p
                className={`text-xs mt-1 ${
                  msg.role === "user" ? "text-gray-400" : "text-indigo-200"
                }`}
              >
                {format(new Date(msg.created_at), "HH:mm")}
              </p>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
