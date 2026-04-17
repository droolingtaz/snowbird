import { useUpcomingEvents } from "../api/hooks";
import Card from "./Card";
import { Calendar, TrendingUp, DollarSign } from "lucide-react";
import { clsx } from "clsx";

const EVENT_ICONS: Record<string, typeof Calendar> = {
  earnings: TrendingUp,
  ex_dividend: Calendar,
  dividend_payment: DollarSign,
};

const EVENT_COLORS: Record<string, string> = {
  earnings: "text-orange-400",
  ex_dividend: "text-blue-400",
  dividend_payment: "text-green-400",
};

const EVENT_LABELS: Record<string, string> = {
  earnings: "Earnings",
  ex_dividend: "Ex-Div",
  dividend_payment: "Payment",
};

export default function UpcomingEventsCard() {
  const { data, isLoading } = useUpcomingEvents(30);
  const events = data?.events ?? [];

  return (
    <Card
      title="Upcoming Events"
      action={
        data && !data.has_finnhub ? (
          <span className="text-2xs text-text-tertiary">dividends only</span>
        ) : null
      }
    >
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse bg-surface-2 rounded h-8" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <p className="text-text-tertiary text-sm py-4 text-center">No upcoming events</p>
      ) : (
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {events.slice(0, 10).map((evt: any, i: number) => {
            const Icon = EVENT_ICONS[evt.event_type] ?? Calendar;
            const color = EVENT_COLORS[evt.event_type] ?? "text-text-secondary";
            const label = EVENT_LABELS[evt.event_type] ?? evt.event_type;
            return (
              <div key={i} className="flex items-start gap-2 text-sm">
                <Icon className={clsx("w-4 h-4 mt-0.5 shrink-0", color)} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-medium">{evt.symbol}</span>
                    <span className={clsx("text-2xs px-1 py-0.5 rounded", color, "bg-surface-2")}>
                      {label}
                    </span>
                  </div>
                  <div className="text-text-tertiary text-xs truncate">
                    {evt.date}
                    {evt.details?.length > 0 && (
                      <span className="ml-1.5">
                        {evt.details.map((d: any) => d.value).filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
