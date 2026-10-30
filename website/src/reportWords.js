// WHAT A REPORT READS AND WHEN IT RUNS, in words (ReportsView's list and the report on the table, ItemSections) - kept apart so the Assistant's card
// can say it without loading the whole Reports tab
// A cron line, said in words when it is one of the shapes people actually write; the raw
// expression stays for anything cleverer, because a wrong paraphrase is worse than none.
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const cronText = (expr) => {
  const f = String(expr || "").trim().split(/\s+/);
  if (f.length !== 5) return `cron ${expr}`;
  const [mi, h, dom, mon, dow] = f;
  const hhmm = /^\d+$/.test(mi) && /^\d+$/.test(h) ? `${String(h).padStart(2, "0")}:${String(mi).padStart(2, "0")}` : null;
  const every = (x, unit) => { const m = /^\*\/(\d+)$/.exec(x); return m ? `every ${m[1]}${unit}` : null; };
  if (h === "*" && dom === "*" && mon === "*" && dow === "*") return every(mi, "m") || (mi === "*" ? "every minute" : `cron ${expr}`);
  if (mi !== "*" && dom === "*" && mon === "*" && dow === "*") return every(h, "h") ? `${every(h, "h")} at :${String(mi).padStart(2, "0")}` : hhmm ? `daily ${hhmm}` : `cron ${expr}`;
  if (hhmm && dom === "*" && mon === "*") {
    if (dow === "1-5") return `weekdays ${hhmm}`;
    if (dow === "0,6" || dow === "6,0") return `weekends ${hhmm}`;
    const days = dow.split(",").map((d) => DOW[Number(d) % 7]).filter(Boolean);
    if (days.length && days.length === dow.split(",").length) return `${days.join(", ")} ${hhmm}`;
  }
  if (hhmm && mon === "*" && dow === "*" && /^\d+$/.test(dom)) return `the ${dom}${["th", "st", "nd", "rd"][(dom % 10 > 3 || [11, 12, 13].includes(dom % 100)) ? 0 : dom % 10]} of the month ${hhmm}`;
  return `cron ${expr}`;
};

// "on app startup" is a lie next to once_per_day/once_per_week - it fires on the FIRST launch of the
// day (or week) and drops the rest. Saying "every" is what made one evening launch look like a restart.
export const startupText = (c) => "on app startup" + (c.once_per_day ? " (at most once a day)"
  : c.once_per_week ? " (at most once a week)" : "");
export const reportSchedule = (c) => [c.on_startup && startupText(c), c.cron && cronText(c.cron),
  c.every_minutes && `every ${c.every_minutes} minutes`, c.daily_at && `daily at ${c.daily_at}`]
  .filter(Boolean).join(" + ") || "only when you press Run now";

export const TYPE_LABELS = {
  zoho_monthly_invoices: "Monthly Zoho invoices", taskuary: "Taskuary", taskuary_data: "Taskuary - its own rows",
  mssql: "SQL Server", winrm: "Remote Windows", mcp: "MCP server", sqlite: "SQLite", rest: "REST / JSON", graphql: "GraphQL", rss: "RSS / Atom",
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
  fmp_fundamentals: "FMP — fundamentals", fmp_ratios: "FMP — ratios", alpaca_quotes: "Alpaca — quotes", alpaca_bars: "Alpaca — bars",
  markets_screen: "Strategy screen — only the rows that match",
  metric: "A certified number (Assistant \u2192 Numbers)", metric_check: "Re-prove the certified numbers",
  digest: "Taskuary digest", evening_inbox: "End-of-day brief", automate: "Automation ideas (own data)", assistant: "Advisor — its notes for you (how it speaks: Settings, Docs)",
  agent: "AI agent — run a skill or a prompt",
  local_file: "File on this computer",
  google_sheets: "Google Sheet", sharepoint_list: "SharePoint list", sharepoint_file: "SharePoint file",
  exa: "Exa — search the web", tavily: "Tavily — search + answer",
  firecrawl: "Firecrawl — read a page", reader: "Jina Reader — read a page (no key)",
};
