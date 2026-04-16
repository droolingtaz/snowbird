import Card from "../components/Card";
import OrderTicket from "../components/OrderTicket";
import { useAuthStore } from "../store/auth";

export default function Trade() {
  const accountId = useAuthStore((s) => s.accountId);

  if (!accountId) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <p className="text-text-secondary">No account selected.</p>
        <a href="/settings" className="btn-primary">Add Alpaca Account</a>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Trade</h1>
      <div className="max-w-md">
        <Card title="Order Ticket">
          <OrderTicket />
        </Card>
      </div>
    </div>
  );
}
