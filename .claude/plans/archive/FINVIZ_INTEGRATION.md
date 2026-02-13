# Finviz Elite API Integration

This document explains how to use the Finviz Elite API integration in the LEAPS Trader application.

## Prerequisites

1. **Finviz Elite Subscription** ($39.50/month or $299.50/year)
   - Sign up at: https://finviz.com/elite
   - Provides access to export API and advanced screening features

2. **API Token**
   - After subscribing, you'll receive an API token
   - This token is used to authenticate export requests

## Setup

### 1. Configure API Token

Add your Finviz Elite API token to the backend configuration:

```bash
# Option A: Environment Variable
export FINVIZ_API_TOKEN="your_api_token_here"

# Option B: .env file
echo "FINVIZ_API_TOKEN=your_api_token_here" >> backend/.env
```

### 2. Restart Backend

The Finviz service initializes on startup:

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

You should see in the logs:
```
Finviz Elite API enabled
```

## Usage

### API Endpoint: `/api/v1/screener/screen/finviz`

This endpoint uses Finviz for pre-screening, then runs detailed LEAPS analysis.

#### Example Request (JavaScript):

```javascript
const response = await fetch('http://localhost:8000/api/v1/screener/screen/finviz', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    market_cap_min: 1000000000,      // $1B
    market_cap_max: 50000000000,     // $50B
    revenue_growth_min: 20,          // 20% YoY
    eps_growth_min: 15,              // 15% YoY
    sector: "Technology",
    top_n: 15,
    criteria: {
      rsi_min: 40,
      rsi_max: 70,
      iv_max: 70
    }
  })
});

const data = await response.json();
console.log('Results:', data.results);
```

#### Example Request (Python):

```python
import requests

response = requests.post('http://localhost:8000/api/v1/screener/screen/finviz', json={
    "market_cap_min": 1_000_000_000,
    "market_cap_max": 50_000_000_000,
    "revenue_growth_min": 20,
    "eps_growth_min": 15,
    "sector": "Technology",
    "top_n": 15,
    "criteria": {
        "rsi_min": 40,
        "rsi_max": 70,
        "iv_max": 70
    }
})

data = response.json()
print(f"Found {data['total_passed']} stocks passing all filters")
```

#### Using Custom Finviz Filter Codes:

For advanced users, you can pass custom Finviz filter codes directly:

```javascript
{
  "finviz_filters": {
    "cap_midover": "",           // Market cap > $2B
    "fa_salesqoq_pos": "",       // Positive sales Q/Q growth
    "fa_epsqoq_pos": "",         // Positive EPS Q/Q growth
    "ta_rsi_os40": "",           // RSI oversold (< 40)
    "sec_technology": ""         // Technology sector
  },
  "top_n": 15
}
```

### Common Finviz Filter Codes

**Market Cap:**
- `cap_smallover`: > $300M
- `cap_midover`: > $2B
- `cap_largeover`: > $10B
- `cap_mega`: > $200B

**Fundamentals:**
- `fa_salesqoq_pos`: Sales Q/Q growth positive
- `fa_epsqoq_pos`: EPS Q/Q growth positive
- `fa_eps5years_pos`: EPS 5Y growth positive
- `fa_roe_o15`: ROE > 15%
- `fa_debteq_u1`: Debt/Equity < 1

**Technical:**
- `ta_rsi_os30`: RSI oversold (< 30)
- `ta_rsi_os40`: RSI oversold (< 40)
- `ta_rsi_ob60`: RSI overbought (> 60)
- `ta_rsi_ob70`: RSI overbought (> 70)
- `ta_sma20_pa`: Price above SMA20
- `ta_sma50_pa`: Price above SMA50
- `ta_sma200_pa`: Price above SMA200

**Sectors:**
- `sec_technology`: Technology
- `sec_healthcare`: Healthcare
- `sec_financial`: Financial
- `sec_consumer_cyclical`: Consumer Cyclical
- `sec_industrials`: Industrials
- `sec_energy`: Energy

Full filter reference: https://finviz.com/help/screener.ashx

## How It Works

1. **Pre-Screening with Finviz**
   - Your criteria are mapped to Finviz filter codes
   - Finviz API returns a CSV of matching stocks (typically 100-500 stocks)
   - Fast execution (< 2 seconds)

2. **Detailed LEAPS Screening**
   - Each stock from Finviz is analyzed through our 4-stage screening:
     - Fundamental filter (revenue/earnings growth, debt, margins)
     - Technical filter (RSI, MACD, SMAs, breakouts)
     - Options filter (LEAPS availability, IV, liquidity)
     - Composite scoring (40% fundamental + 30% technical + 20% options + 10% momentum)

3. **Results**
   - Top N stocks passing all filters
   - Detailed scores and metrics for each
   - LEAPS option recommendations

## Benefits vs. Yahoo Finance Only

| Aspect | Yahoo Finance | Finviz Elite |
|--------|---------------|--------------|
| **Initial Universe** | Manual symbol list | Automated filtering of 8000+ stocks |
| **Fundamental Filters** | Downloaded per-stock | Pre-filtered on server |
| **Speed** | Slower (1 req/sec limit) | Faster (bulk export) |
| **Data Depth** | Real-time prices, options | 8 years financials, 72+ filters |
| **Cost** | Free | $39.50/month or $299.50/year |

## Recommendation

**Use Finviz Elite if:**
- You want to scan the entire market (thousands of stocks)
- You need 72+ fundamental filters
- You want faster screening execution
- You have a paid subscription

**Use Yahoo Finance if:**
- You're screening a specific watchlist (< 50 stocks)
- You want real-time prices and options data
- You're on a budget (free tier)

**Best of Both Worlds:**
Use Finviz for initial universe filtering (thousands → hundreds), then Yahoo Finance for detailed analysis and real-time options data.

## Troubleshooting

### Error: "Finviz Elite API not configured"

Solution: Add `FINVIZ_API_TOKEN` to your environment or `.env` file

### Error: "HTTP 403 Forbidden"

Solution: Check that your API token is valid and your subscription is active

### No Results Returned

Solution: Try relaxing your filter criteria (lower growth thresholds, wider market cap range)

## Support

- Finviz Help: https://finviz.com/help/
- Finviz Elite: https://finviz.com/elite
