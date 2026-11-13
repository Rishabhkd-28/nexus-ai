import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import { formatDistanceToNow } from "date-fns";

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

const CHANNEL_CONFIG = {
  whatsapp:     { icon: "💬", label: "WhatsApp",        badge: "bg-green-100 text-green-700" },
  whatsapp_dev: { icon: "🛠️", label: "WhatsApp (You)",  badge: "bg-teal-100 text-teal-700" },
  email:        { icon: "📧", label: "Email",           badge: "bg-sky-100 text-sky-700" },
  instagram:    { icon: "📸", label: "Instagram",       badge: "bg-pink-100 text-pink-700" },
};

export default function LeadTable({ onSelectLead, selectedLeadId, filterChannel, channelFilter }) {
  const [leads, setLeads] = useState([]);

  useEffect(() => {
    fetchLeads();
    const ch = supabase
      .channel("leads-realtime")
      .on("postgres_changes", { event: "*", schema: "public", table: "leads" }, fetchLeads)
      .subscribe();
    return () => supabase.removeChannel(ch);
  }, []);

  async function fetchLeads() {
    let query = supabase.from("leads").select("*").order("created_at", { ascending: false });
    if (filterChannel) {
      query = query.eq("channel", filterChannel);
    } else if (channelFilter && channelFilter.length > 0) {
      query = query.in("channel", channelFilter);
    }
    const { data } = await query;
    if (data) setLeads(data);
  }

  async function handleTakeover(e, leadId) {
    e.stopPropagation();
    await supabase.from("leads")
      .update({ human_takeover: true, stage: "HUMAN_TAKEOVER" })
      .eq("id", leadId);
  }

  async function handleRelease(e, leadId) {
    e.stopPropagation();
    await supabase.from("leads")
      .update({ human_takeover: false, stage: "QUALIFYING" })
      .eq("id", leadId);
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <h2 className="font-semibold text-gray-900">Leads</h2>
        <span className="text-sm text-gray-500">{leads.length} total</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
              <th className="px-4 py-3">Channel</th>
              <th className="px-4 py-3">Lead</th>
              <th className="px-4 py-3">Stage</th>
              <th className="px-4 py-3">Rep</th>
              <th className="px-4 py-3">Arrived</th>
              <th className="px-4 py-3">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {leads.map((lead) => {
              const ch = CHANNEL_CONFIG[lead.channel] || { icon: "?", label: lead.channel, badge: "bg-gray-100 text-gray-600" };
              return (
                <tr
                  key={lead.id}
                  onClick={() => onSelectLead(lead)}
                  className={`cursor-pointer hover:bg-gray-50 transition-colors ${
                    selectedLeadId === lead.id ? "bg-indigo-50" : ""
                  }`}
                >
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${ch.badge}`}>
                      {ch.icon} {ch.label}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900 truncate max-w-[140px]">
                      {lead.sender_name?.split(" | ")[0] || lead.sender_id}
                    </div>
                    <div className="text-xs text-gray-400 truncate max-w-[140px]">
                      {lead.sender_id}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                      STAGE_COLORS[lead.stage] || "bg-gray-100 text-gray-600"
                    }`}>
                      {lead.stage}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-700">
                    {lead.assigned_rep || <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {formatDistanceToNow(new Date(lead.created_at), { addSuffix: true })}
                  </td>
                  <td className="px-4 py-3">
                    {lead.human_takeover ? (
                      <button
                        onClick={(e) => handleRelease(e, lead.id)}
                        className="text-xs px-2 py-1 rounded bg-green-100 text-green-700 hover:bg-green-200 transition-colors"
                      >
                        Release to AI
                      </button>
                    ) : (
                      <button
                        onClick={(e) => handleTakeover(e, lead.id)}
                        className="text-xs px-2 py-1 rounded bg-orange-100 text-orange-700 hover:bg-orange-200 transition-colors"
                      >
                        Take Over
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
            {leads.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-gray-400">
                  No leads yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
