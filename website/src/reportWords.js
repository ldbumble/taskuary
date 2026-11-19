import { useEffect, useState } from "react";
import api from "./api";
import { READ_LABELS } from "./apiReads.js";
// WHAT A REPORT READS AND WHEN IT RUNS, in words (ReportsView's list and the report on the table, ItemSections) - kept apart so the Assistant's card
// can say it without loading the whole Reports tab
// WHEN IT RUNS is the SERVER's to say, once (reports.schedule_words): a saved row carries it as ScheduleWords, and a clock an editor holds
// unsaved is asked of the same function (/api/schedule-words). The page had three sayings of its own - "daily 08:00" in the list, "every day
// at 08:00" in the routine's editor, "daily at 08:00" on its task - for one routine.
export function useScheduleWords(cfg) {
  const key = JSON.stringify(cfg || {});
  const [words, setWords] = useState("");
  useEffect(() => {
    let live = true;
    const t = setTimeout(() => api.post("/api/schedule-words", { cfg: JSON.parse(key) })
      .then(({ data }) => { if (live) setWords(data?.words || ""); }).catch(() => {}), 150);
    return () => { live = false; clearTimeout(t); };
  }, [key]);
  return words;
}

export const TYPE_LABELS = {
  ...READ_LABELS,
  zoho_monthly_invoices: "Monthly Zoho invoices", taskuary: "Taskuary", taskuary_data: "Taskuary - its own rows",
  obsidian_read: "Obsidian notes", mssql: "SQL Server", winrm: "Remote Windows", mcp: "MCP server", sqlite: "SQLite", rest: "REST / JSON", graphql: "GraphQL", rss: "RSS / Atom",
  database: "Any database", aws: "AWS (any call)", s3_object: "S3 object", cloudwatch_logs: "CloudWatch logs",
  azure: "Azure (ARM)", azure_blob: "Azure blob", azure_logs: "Azure Log Analytics",
  entra_users: "Entra ID — people", entra_groups: "Entra ID — group members",
  entra_signins: "Entra ID — sign-ins", entra_licenses: "Entra ID — licence seats",
  prometheus: "Prometheus", datadog: "Datadog monitors",
  intacct: "Sage Intacct", intacct_fields: "Intacct \u2014 what fields exist",
  quickbooks: "QuickBooks Online", quickbooks_vendors: "QuickBooks \u2014 vendors", quickbooks_accounts: "QuickBooks \u2014 chart of accounts",
  amazon_sales_traffic: "Amazon \u2014 sales & traffic", amazon_orders: "Amazon \u2014 orders by order date",
  amazon_inventory: "Amazon \u2014 FBA inventory", amazon_settlement: "Amazon \u2014 settlement",
  amazon_report: "Amazon \u2014 any report", amazon_marketplaces: "Amazon \u2014 marketplaces",
  amazon_business_transactions: "Amazon \u2014 Business purchases",
  stripe_balance: "Stripe \u2014 balance", stripe_balance_transactions: "Stripe \u2014 balance transactions (fees & net)",
  stripe_charges: "Stripe \u2014 charges", stripe_payments: "Stripe \u2014 payments", stripe_payouts: "Stripe \u2014 payouts",
  stripe_refunds: "Stripe \u2014 refunds", stripe_disputes: "Stripe \u2014 disputes", stripe_customers: "Stripe \u2014 customers",
  stripe_subscriptions: "Stripe \u2014 subscriptions (MRR)", stripe_invoices: "Stripe \u2014 invoices",
  teller_transactions: "Bank & card \u2014 transactions", teller_accounts: "Bank & card \u2014 accounts", teller_balances: "Bank & card \u2014 balances",
  teller_spend: "Bank & card — spend, per card and in total",
  simplefin_transactions: "Bank & card (SimpleFIN) \u2014 transactions", simplefin_accounts: "Bank & card (SimpleFIN) \u2014 accounts",
  simplefin_balances: "Bank & card (SimpleFIN) \u2014 balances", simplefin_spend: "Bank & card (SimpleFIN) \u2014 spend, per account and in total",
  yahoo_quotes: "Yahoo Finance — quotes", yahoo_history: "Yahoo Finance — price history",
  coingecko_prices: "Crypto prices (CoinGecko)", alchemy_prices: "Alchemy — token prices", alchemy_wallet: "Alchemy — wallet holdings", fx_rates: "FX rates", fred_series: "FRED — macro series",
  edgar_filings: "SEC EDGAR — filings", edgar_facts: "SEC EDGAR — one reported number over time",
  td_quotes: "Twelve Data — quotes", td_indicator: "Twelve Data — technical indicator", av_quotes: "Alpha Vantage — quotes",
  finnhub_quotes: "Finnhub — quotes", finnhub_news: "Finnhub — company news", finnhub_earnings: "Finnhub — earnings", finnhub_insiders: "Finnhub — insider transactions",
  polygon_bars: "Polygon.io — bars", polygon_snapshot: "Polygon.io — snapshot", tiingo_history: "Tiingo — price history", tiingo_news: "Tiingo — news",
  marketstack_eod: "Marketstack — end-of-day bars", eodhd_eod: "EOD Historical Data — end-of-day bars",
  fmp_fundamentals: "FMP — fundamentals", fmp_ratios: "FMP — ratios", alpaca_quotes: "Alpaca — quotes", alpaca_bars: "Alpaca — bars",
  markets_screen: "Strategy screen — only the rows that match",
  metric: "A certified number (Assistant \u2192 Numbers)", metric_check: "Re-prove the certified numbers",
  digest: "Taskuary digest", evening_inbox: "End-of-day brief", automate: "Automation ideas (own data)", assistant: "Advisor — its notes for you (how it speaks: Settings, Docs)",
  agent: "AI agent — run a skill or a prompt",
  local_file: "File on this computer", python_script: "Python script on this computer",
  google_sheets: "Google Sheet", sharepoint_list: "SharePoint list", sharepoint_file: "SharePoint file",
  exa: "Exa — search the web", tavily: "Tavily — search + answer",
  firecrawl: "Firecrawl — read a page", reader: "Jina Reader — read a page (no key)",
};
