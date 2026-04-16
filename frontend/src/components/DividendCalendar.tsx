interface CalendarItem {
  symbol: string;
  ex_date?: string;
  pay_date?: string;
  amount_per_share?: number;
  projected_income?: number;
}

export default function DividendCalendar({ items }: { items: CalendarItem[] }) {
  if (!items?.length) {
    return (
      <div className="text-center py-8 text-text-tertiary text-sm">
        No upcoming dividends projected. Add positions to see estimates.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="table-auto">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Ex-Date</th>
            <th>Pay Date</th>
            <th className="text-right">$/Share</th>
            <th className="text-right">Est. Income</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => (
            <tr key={`${item.symbol}-${item.pay_date}-${i}`}>
              <td className="font-semibold">{item.symbol}</td>
              <td className="text-text-secondary">{item.ex_date ?? "—"}</td>
              <td className="text-text-secondary">{item.pay_date ?? "—"}</td>
              <td className="text-right mono">
                {item.amount_per_share != null ? `$${item.amount_per_share.toFixed(4)}` : "—"}
              </td>
              <td className="text-right mono text-green-profit">
                {item.projected_income != null ? `$${item.projected_income.toFixed(2)}` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
