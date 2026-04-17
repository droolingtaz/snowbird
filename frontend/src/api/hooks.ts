import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "./client";
import { useAuthStore } from "../store/auth";

// ── Helpers ──────────────────────────────────────────────────────────────────

function useAccountId() {
  return useAuthStore((s) => s.accountId);
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me").then((r) => r.data),
    retry: false,
  });
}

// ── Accounts ─────────────────────────────────────────────────────────────────

export function useAccounts() {
  return useQuery({
    queryKey: ["accounts"],
    queryFn: () => api.get("/accounts").then((r) => r.data),
  });
}

export function useCreateAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      api.post("/accounts", data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  });
}

export function useDeleteAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete(`/accounts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  });
}

export function useTestAccount() {
  return useMutation({
    mutationFn: (id: number) => api.post(`/accounts/${id}/test`).then((r) => r.data),
  });
}

export function useSyncAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.post(`/accounts/${id}/sync`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["holdings"] });
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      qc.invalidateQueries({ queryKey: ["orders"] });
    },
  });
}

// ── Portfolio ─────────────────────────────────────────────────────────────────

export function usePortfolioSummary() {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["portfolio", "summary", accountId],
    queryFn: () =>
      api.get("/portfolio/summary", { params: { account_id: accountId } }).then((r) => r.data),
    enabled: !!accountId,
    refetchInterval: 30_000,
  });
}

export function usePortfolioHistory(period: string = "1M") {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["portfolio", "history", accountId, period],
    queryFn: () =>
      api
        .get("/portfolio/history", { params: { account_id: accountId, period, timeframe: "1D" } })
        .then((r) => r.data),
    enabled: !!accountId,
  });
}

export function usePortfolioAllocation(by: string = "sector") {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["portfolio", "allocation", accountId, by],
    queryFn: () =>
      api
        .get("/portfolio/allocation", { params: { account_id: accountId, by } })
        .then((r) => r.data),
    enabled: !!accountId,
  });
}

// ── Holdings ──────────────────────────────────────────────────────────────────

export function useHoldings() {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["holdings", accountId],
    queryFn: () =>
      api.get("/holdings", { params: { account_id: accountId } }).then((r) => r.data),
    enabled: !!accountId,
    refetchInterval: 30_000,
  });
}

// ── Orders ────────────────────────────────────────────────────────────────────

export function useOrders(status: "open" | "closed" | "all" = "all") {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["orders", accountId, status],
    queryFn: () =>
      api.get("/orders", { params: { account_id: accountId, status } }).then((r) => r.data),
    enabled: !!accountId,
    refetchInterval: status === "open" ? 10_000 : undefined,
  });
}

export function usePlaceOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      api.post("/orders", data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orders"] }),
  });
}

export function useCancelOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, accountId }: { orderId: number; accountId: number }) =>
      api.delete(`/orders/${orderId}`, { params: { account_id: accountId } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orders"] }),
  });
}

export function useCancelAllOrders() {
  const qc = useQueryClient();
  const accountId = useAccountId();
  return useMutation({
    mutationFn: () => api.delete("/orders", { params: { account_id: accountId } }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orders"] }),
  });
}

// ── Dividends ─────────────────────────────────────────────────────────────────

export function useDividendHistory(year?: number) {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["dividends", "history", accountId, year],
    queryFn: () =>
      api
        .get("/dividends/history", { params: { account_id: accountId, year } })
        .then((r) => r.data),
    enabled: !!accountId,
  });
}

export function useDividendForecast() {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["dividends", "forecast", accountId],
    queryFn: () =>
      api.get("/dividends/forecast", { params: { account_id: accountId } }).then((r) => r.data),
    enabled: !!accountId,
  });
}

export function useDividendCalendar(from: string, to: string) {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["dividends", "calendar", accountId, from, to],
    queryFn: () =>
      api
        .get("/dividends/calendar", { params: { account_id: accountId, from, to } })
        .then((r) => r.data),
    enabled: !!accountId && !!from && !!to,
  });
}

export function useDividendsBySymbol() {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["dividends", "by-symbol", accountId],
    queryFn: () =>
      api.get("/dividends/by-symbol", { params: { account_id: accountId } }).then((r) => r.data),
    enabled: !!accountId,
  });
}

export function useFuturePayments(months: number = 12) {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["dividends", "future-payments", accountId, months],
    queryFn: () =>
      api
        .get("/dividends/future-payments", { params: { account_id: accountId, months } })
        .then((r) => r.data),
    enabled: !!accountId,
  });
}

export function useReceivedMonthly(months: number = 12) {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["dividends", "received-monthly", accountId, months],
    queryFn: () =>
      api
        .get("/dividends/received-monthly", { params: { account_id: accountId, months } })
        .then((r) => r.data),
    enabled: !!accountId,
  });
}

export function useGrowthYoY(years: number = 3) {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["dividends", "growth-yoy", accountId, years],
    queryFn: () =>
      api
        .get("/dividends/growth-yoy", { params: { account_id: accountId, years } })
        .then((r) => r.data),
    enabled: !!accountId,
  });
}

// ── Analytics ─────────────────────────────────────────────────────────────────

export function usePerformance(period: string = "1Y") {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["analytics", "performance", accountId, period],
    queryFn: () =>
      api
        .get("/analytics/performance", { params: { account_id: accountId, period } })
        .then((r) => r.data),
    enabled: !!accountId,
  });
}

export function useBenchmark(symbol: string = "SPY", period: string = "1Y") {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["analytics", "benchmark", accountId, symbol, period],
    queryFn: () =>
      api
        .get("/analytics/benchmark", { params: { account_id: accountId, symbol, period } })
        .then((r) => r.data),
    enabled: !!accountId,
  });
}

export function useMonthlyReturns() {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["analytics", "monthly", accountId],
    queryFn: () =>
      api.get("/analytics/monthly", { params: { account_id: accountId } }).then((r) => r.data),
    enabled: !!accountId,
  });
}

export function useIrr(period: string = "1Y") {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["analytics", "irr", accountId, period],
    queryFn: () =>
      api.get("/analytics/irr", { params: { account_id: accountId, period } }).then((r) => r.data),
    enabled: !!accountId,
  });
}

export function usePassiveIncome() {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["analytics", "passive-income", accountId],
    queryFn: () =>
      api.get("/analytics/passive-income", { params: { account_id: accountId } }).then((r) => r.data),
    enabled: !!accountId,
  });
}

export function useMovers(limit: number = 5) {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["analytics", "movers", accountId, limit],
    queryFn: () =>
      api.get("/analytics/movers", { params: { account_id: accountId, limit } }).then((r) => r.data),
    enabled: !!accountId,
    refetchInterval: 30_000,
  });
}

// ── Buckets ───────────────────────────────────────────────────────────────────

export function useBuckets() {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["buckets", accountId],
    queryFn: () =>
      api.get("/buckets", { params: { account_id: accountId } }).then((r) => r.data),
    enabled: !!accountId,
  });
}

export function useBucketDrift() {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["buckets", "drift", accountId],
    queryFn: () =>
      api.get("/buckets/drift", { params: { account_id: accountId } }).then((r) => r.data),
    enabled: !!accountId,
  });
}

export function useRebalancePreview(cashToDeploy: number = 0) {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["buckets", "rebalance", accountId, cashToDeploy],
    queryFn: () =>
      api
        .get("/buckets/rebalance", { params: { account_id: accountId, cash_to_deploy: cashToDeploy } })
        .then((r) => r.data),
    enabled: !!accountId,
  });
}

export function useCreateBucket() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      api.post("/buckets", data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["buckets"] }),
  });
}

export function useUpdateBucket() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      api.put(`/buckets/${id}`, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["buckets"] }),
  });
}

export function useDeleteBucket() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete(`/buckets/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["buckets"] }),
  });
}

export function useExecuteRebalance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      api.post("/buckets/rebalance/execute", data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["holdings"] });
    },
  });
}

// ── Market ────────────────────────────────────────────────────────────────────

export function useMarketSearch(q: string) {
  return useQuery({
    queryKey: ["market", "search", q],
    queryFn: () => api.get("/market/search", { params: { q } }).then((r) => r.data),
    enabled: q.length >= 1,
    staleTime: 60_000,
  });
}

export function useMarketQuote(symbol: string) {
  return useQuery({
    queryKey: ["market", "quote", symbol],
    queryFn: () => api.get("/market/quote", { params: { symbol } }).then((r) => r.data),
    enabled: !!symbol,
    refetchInterval: 10_000,
  });
}

export function useMarketClock() {
  return useQuery({
    queryKey: ["market", "clock"],
    queryFn: () => api.get("/market/clock").then((r) => r.data),
    refetchInterval: 60_000,
  });
}


// ── Events ────────────────────────────────────────────────────────────────────

export function useUpcomingEvents(days: number = 30) {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["events", "upcoming", accountId, days],
    queryFn: () =>
      api.get("/events/upcoming", { params: { account_id: accountId, days } }).then((r) => r.data),
    enabled: !!accountId,
    staleTime: 5 * 60_000,
  });
}

// ── Goals ─────────────────────────────────────────────────────────────────────

export function useGoal() {
  return useQuery({
    queryKey: ["goals"],
    queryFn: () => api.get("/goals").then((r) => r.data),
    retry: false,
  });
}

export function useUpsertGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { target_annual_income: number; assumed_annual_growth_pct?: number; assumed_monthly_contribution?: number }) =>
      api.put("/goals", data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["goals"] });
      qc.invalidateQueries({ queryKey: ["goals", "projection"] });
    },
  });
}

export function useGoalProjection() {
  const accountId = useAccountId();
  return useQuery({
    queryKey: ["goals", "projection", accountId],
    queryFn: () =>
      api.get("/goals/projection", { params: { account_id: accountId } }).then((r) => r.data),
    enabled: !!accountId,
    retry: false,
  });
}
