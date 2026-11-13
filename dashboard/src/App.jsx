import { useEffect, useState } from "react";
import { supabase } from "./lib/supabase";
import LeadTable from "./components/LeadTable";
import ConversationPanel from "./components/ConversationPanel";
import ActionLog from "./components/ActionLog";
import MeetingBoard from "./components/MeetingBoard";
import EmailPanel from "./components/EmailPanel";

const TABS = [
  { id: "whatsapp", label: "💬 WhatsApp" },
  { id: "email",    label: "📧 Email" },
  { id: "meetings", label: "📅 Meetings" },
  { id: "log",      label: "📋 Activity" },
  { id: "instagram",label: "📸 Instagram", comingSoon: true },
];

export default function App() {
  const [session, setSession]       = useState(null);
  const [loading, setLoading]       = useState(true);
  const [selectedLead, setSelected] = useState(null);
  const [activeTab, setActiveTab]   = useState("whatsapp");
  const [email, setEmail]           = useState("");
  const [password, setPassword]     = useState("");
  const [authError, setAuthError]   = useState("");

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    supabase.auth.onAuthStateChange((_e, s) => setSession(s));
  }, []);

  async function handleLogin(e) {
    e.preventDefault();
    setAuthError("");
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) setAuthError(error.message);
  }

  async function handleLogout() {
    await supabase.auth.signOut();
    setSelected(null);
  }

  if (loading) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-gray-400">Loading…</div>
    </div>
  );

  if (!session) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8 w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-3xl mb-2">🤖</div>
          <h1 className="text-xl font-bold text-gray-900">Nexus AI</h1>
          <p className="text-sm text-gray-500 mt-1">Sales Dashboard</p>
        </div>
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="admin@nexusanalytics.in" required />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              required />
          </div>
          {authError && <p className="text-sm text-red-600">{authError}</p>}
          <button type="submit"
            className="w-full bg-indigo-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-indigo-700 transition-colors">
            Sign In
          </button>
        </form>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Nav */}
      <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <span className="text-xl">🤖</span>
            <span className="font-bold text-gray-900">Nexus AI</span>
          </div>
          <div className="flex gap-1">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => !tab.comingSoon && setActiveTab(tab.id)}
                className={`relative px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  tab.comingSoon
                    ? "text-gray-300 cursor-not-allowed"
                    : activeTab === tab.id
                    ? "bg-indigo-100 text-indigo-700"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                {tab.label}
                {tab.comingSoon && (
                  <span className="absolute -top-1 -right-1 text-[9px] bg-yellow-100 text-yellow-700 px-1 rounded-full font-semibold leading-4">
                    soon
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
        <button onClick={handleLogout} className="text-sm text-gray-500 hover:text-gray-900">
          Sign out
        </button>
      </nav>

      {/* Content */}
      <div className="max-w-7xl mx-auto p-6">

        {/* WhatsApp tab — shows both whatsapp + whatsapp_dev leads */}
        {activeTab === "whatsapp" && (
          <div className="space-y-6">
            {/* Dev number callout */}
            <div className="bg-teal-50 border border-teal-200 rounded-xl px-5 py-3 flex items-center gap-3 text-sm">
              <span className="text-lg">🛠️</span>
              <div>
                <span className="font-medium text-teal-800">Your number is connected as a dev channel.</span>
                <span className="text-teal-600 ml-1">
                  Leads from it appear with a "WhatsApp (You)" badge — same AI, separate tracking.
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              <div className="space-y-6">
                <LeadTable
                  onSelectLead={setSelected}
                  selectedLeadId={selectedLead?.id}
                  filterChannel={null}   // show all WA channels
                  channelFilter={["whatsapp", "whatsapp_dev"]}
                />
                <ActionLog leadId={selectedLead?.id} />
              </div>
              <ConversationPanel lead={selectedLead} />
            </div>
          </div>
        )}

        {/* Email tab */}
        {activeTab === "email" && <EmailPanel />}

        {/* Meetings tab */}
        {activeTab === "meetings" && <MeetingBoard />}

        {/* Activity tab */}
        {activeTab === "log" && <ActionLog />}

      </div>
    </div>
  );
}
