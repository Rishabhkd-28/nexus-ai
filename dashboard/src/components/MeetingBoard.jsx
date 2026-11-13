import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import { format, isPast } from "date-fns";

const REP_COLORS = {
  Arjun: "bg-blue-100 text-blue-800 border-blue-200",
  Priya: "bg-pink-100 text-pink-800 border-pink-200",
};

export default function MeetingBoard() {
  const [bookings, setBookings] = useState([]);

  useEffect(() => {
    fetchBookings();

    const ch = supabase
      .channel("bookings-realtime")
      .on("postgres_changes", { event: "*", schema: "public", table: "bookings" }, () => {
        fetchBookings();
      })
      .subscribe();

    return () => supabase.removeChannel(ch);
  }, []);

  async function fetchBookings() {
    const { data } = await supabase
      .from("bookings")
      .select("*, leads(sender_name, sender_id, channel)")
      .order("slot_start", { ascending: true });
    if (data) setBookings(data);
  }

  const upcoming = bookings.filter((b) => !isPast(new Date(b.slot_start)));
  const past     = bookings.filter((b) =>  isPast(new Date(b.slot_start)));

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <h2 className="font-semibold text-gray-900">Bookings</h2>
        <div className="flex gap-2 text-xs">
          <span className="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">
            {upcoming.length} upcoming
          </span>
          <span className="bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
            {past.length} past
          </span>
        </div>
      </div>

      <div className="divide-y divide-gray-50 max-h-[400px] overflow-y-auto">
        {upcoming.map((b) => (
          <BookingRow key={b.id} booking={b} dim={false} />
        ))}
        {past.map((b) => (
          <BookingRow key={b.id} booking={b} dim={true} />
        ))}
        {bookings.length === 0 && (
          <div className="px-6 py-10 text-center text-gray-400 text-sm">
            No bookings yet
          </div>
        )}
      </div>
    </div>
  );
}

function BookingRow({ booking: b, dim }) {
  const lead = b.leads || {};
  const calLink = b.calendar_event_id
    ? `https://calendar.google.com/calendar/event?eid=${b.calendar_event_id}`
    : null;

  return (
    <div className={`px-6 py-4 flex items-center gap-4 ${dim ? "opacity-50" : ""}`}>
      <div className="text-center min-w-[52px]">
        <div className="text-xs text-gray-400">{format(new Date(b.slot_start), "MMM")}</div>
        <div className="text-2xl font-bold text-gray-800 leading-none">
          {format(new Date(b.slot_start), "d")}
        </div>
        <div className="text-xs text-gray-500">{format(new Date(b.slot_start), "HH:mm")}</div>
      </div>

      <div className="flex-1 min-w-0">
        <p className="font-medium text-gray-900 truncate">
          {lead.sender_name || lead.sender_id}
        </p>
        <p className="text-xs text-gray-400 mt-0.5">
          {format(new Date(b.slot_start), "EEEE, d MMMM")} ·{" "}
          {format(new Date(b.slot_start), "HH:mm")} –{" "}
          {format(new Date(b.slot_end),   "HH:mm")} IST
        </p>
      </div>

      <div className="flex items-center gap-2">
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded border ${
            REP_COLORS[b.rep] || "bg-gray-100 text-gray-600 border-gray-200"
          }`}
        >
          {b.rep}
        </span>
        {calLink && (
          <a
            href={calLink}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-indigo-600 hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            📅 Cal
          </a>
        )}
      </div>
    </div>
  );
}
