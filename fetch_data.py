#!/usr/bin/env python3
"""Hämtar dagliga slutkurser och skriver data.json som sidan läser.

Datakälla:
  - Tiingo om miljövariabeln TIINGO_API_KEY finns (justerade kurser, rekommenderas)
  - annars Stooq (ingen nyckel krävs)

Användning:
  python3 scripts/fetch_data.py                # skriver data.json
  python3 scripts/fetch_data.py --out data.json --days 800
"""
import argparse
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

# (ticker, namn) – samma 50 aktier som i demoversionen. Index = SPY (S&P 500 ETF).
TICKERS = [
    ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA"), ("AMZN", "Amazon"),
    ("GOOGL", "Alphabet"), ("META", "Meta Platforms"), ("TSLA", "Tesla"), ("AVGO", "Broadcom"),
    ("JPM", "JPMorgan Chase"), ("V", "Visa"), ("LLY", "Eli Lilly"), ("COST", "Costco"),
    ("NFLX", "Netflix"), ("AMD", "AMD"), ("CRM", "Salesforce"), ("XOM", "Exxon Mobil"),
    ("UNH", "UnitedHealth"), ("PLTR", "Palantir"), ("ORCL", "Oracle"), ("ADBE", "Adobe"),
    ("WMT", "Walmart"), ("MA", "Mastercard"), ("HD", "Home Depot"), ("PG", "Procter & Gamble"),
    ("JNJ", "Johnson & Johnson"), ("BAC", "Bank of America"), ("KO", "Coca-Cola"),
    ("PEP", "PepsiCo"), ("MRK", "Merck"), ("ABBV", "AbbVie"), ("CVX", "Chevron"),
    ("TMO", "Thermo Fisher"), ("CSCO", "Cisco"), ("MCD", "McDonald's"), ("DIS", "Disney"),
    ("INTC", "Intel"), ("QCOM", "Qualcomm"), ("TXN", "Texas Instruments"), ("NKE", "Nike"),
    ("PYPL", "PayPal"), ("UBER", "Uber"), ("SNOW", "Snowflake"), ("COIN", "Coinbase"),
    ("BA", "Boeing"), ("GS", "Goldman Sachs"), ("WFC", "Wells Fargo"), ("CAT", "Caterpillar"),
    ("IBM", "IBM"), ("MU", "Micron"),
]
INDEX_TICKER = "SPY"
MIN_ROWS = 300          # modellen behöver minst ~260 handelsdagar
MIN_STOCKS = 40         # skriv inte över data.json om för många aktier saknas
UA = {"User-Agent": "Mozilla/5.0 (valora-analytics data job)"}


def http_get(url, tries=3, wait=5):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                time.sleep(60)          # rate limit: vänta en stund
            elif e.code in (400, 401, 403, 404):
                break
            else:
                time.sleep(wait * (i + 1))
        except Exception as e:           # nätverksfel
            last = e
            time.sleep(wait * (i + 1))
    raise RuntimeError(f"misslyckades hämta {url.split('?')[0]}: {last}")


def stooq(ticker, start):
    sym = ticker.lower().replace(".", "-") + ".us"
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d&d1={start:%Y%m%d}&d2={date.today():%Y%m%d}"
    text = http_get(url)
    if "Date" not in text.split("\n", 1)[0]:
        raise RuntimeError(f"oväntat svar från Stooq för {ticker}: {text[:60]!r}")
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            out[row["Date"]] = float(row["Close"])
        except (KeyError, ValueError):
            continue
    return out


def tiingo(ticker, start, key):
    url = (f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
           f"?startDate={start:%Y-%m-%d}&token={key}")
    rows = json.loads(http_get(url))
    return {r["date"][:10]: float(r["adjClose"]) for r in rows if r.get("adjClose")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data.json")
    ap.add_argument("--days", type=int, default=800, help="antal handelsdagar att spara")
    a = ap.parse_args()

    key = os.environ.get("TIINGO_API_KEY", "").strip()
    source = "Tiingo" if key else "Stooq"
    start = date.today() - timedelta(days=int(a.days * 1.5) + 10)
    fetch = (lambda t: tiingo(t, start, key)) if key else (lambda t: stooq(t, start))
    pause = 0.0 if not key else 1.5

    print(f"Källa: {source}, från {start}")
    idx = fetch(INDEX_TICKER)
    if len(idx) < MIN_ROWS:
        sys.exit(f"För lite indexdata ({len(idx)} rader) – avbryter utan att skriva.")
    cal = sorted(idx)[-a.days:]                      # gemensam handelskalender

    stocks, failed = [], []
    for tk, name in TICKERS:
        try:
            time.sleep(pause)
            px = fetch(tk)
            if len(px) < MIN_ROWS:
                raise RuntimeError(f"bara {len(px)} rader")
            series, last = [], None
            for d in cal:
                last = px.get(d, last)               # fyll hål med föregående kurs
                series.append(last)
            first = next((v for v in series if v is not None), None)
            series = [first if v is None else v for v in series]
            if first is None or any(v <= 0 for v in series):
                raise RuntimeError("ogiltiga kurser")
            stocks.append({"k": tk, "n": name, "p": [round(v, 4) for v in series]})
            print(f"  ok  {tk}")
        except Exception as e:
            failed.append(tk)
            print(f"  FEL {tk}: {e}", file=sys.stderr)

    if len(stocks) < MIN_STOCKS:
        sys.exit(f"Bara {len(stocks)} aktier hämtades (krav {MIN_STOCKS}) – data.json lämnas orörd.")

    idx_series, last = [], None
    for d in cal:
        last = idx.get(d, last)
        idx_series.append(last)

    data = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asof": cal[-1],
        "source": source,
        "dates": cal,
        "index": [round(v, 4) for v in idx_series],
        "stocks": stocks,
        "failed": failed,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"Skrev {a.out}: {len(stocks)} aktier, {len(cal)} dagar, senaste {cal[-1]}"
          + (f", saknas: {', '.join(failed)}" if failed else ""))


if __name__ == "__main__":
    main()
