# MacroOverlay Component Manual Test Cases

## Prerequisites

1. Start the backend server:
   ```bash
   cd backend && uvicorn app.main:app --reload --port 8000
   ```

2. Start the frontend dev server:
   ```bash
   cd frontend && npm run dev
   ```

3. Ensure FRED API key is configured in `backend/app/config.py` or environment variables

---

## Test Case 1: API Endpoint Verification

### 1.1 Test macro-overlay endpoint returns valid response

**Steps:**
```bash
curl -s http://localhost:8000/api/v1/command-center/macro-intelligence/ticker/AAPL/macro-overlay | jq .
```

**Expected Response Structure:**
```json
{
  "symbol": "AAPL",
  "sector": "Unknown",
  "macro_bias": "neutral",
  "macro_bias_score": 50.0,
  "confidence_score": 70.0,
  "data_stale": false,
  "trade_compatibility": "mixed",
  "macro_headwind": false,
  "compatibility_flags": { ... },
  "compatibility_reasons": [ ... ],
  "drivers": [
    "Liquidity: Mixed",
    "Fed Policy: Neutral"
  ],
  "earnings": null,
  "details": { ... },
  "links": {
    "macro_intelligence": "/macro-intelligence"
  },
  "calculated_at": "2026-02-02T..."
}
```

**Pass Criteria:**
- [ ] Response returns HTTP 200
- [ ] `symbol` matches requested ticker
- [ ] `macro_bias` is one of: "bearish", "neutral", "bullish", "unknown"
- [ ] `trade_compatibility` is one of: "favorable", "mixed", "unfavorable"
- [ ] `drivers` is an array of human-readable strings
- [ ] `links.macro_intelligence` is "/macro-intelligence"

### 1.2 Test with sector parameter

**Steps:**
```bash
curl -s "http://localhost:8000/api/v1/command-center/macro-intelligence/ticker/AAPL/macro-overlay?sector=Technology" | jq .
```

**Pass Criteria:**
- [ ] `sector` in response is "Technology"
- [ ] `details.sector_weights` shows Technology weights (liquidity: 0.30, fed_policy: 0.25, etc.)

### 1.3 Test different sectors produce different scores

**Steps:**
```bash
# Technology sector
curl -s "http://localhost:8000/api/v1/command-center/macro-intelligence/ticker/AAPL/macro-overlay?sector=Technology" | jq '.macro_bias_score'

# Financials sector (same macro conditions, different weights)
curl -s "http://localhost:8000/api/v1/command-center/macro-intelligence/ticker/JPM/macro-overlay?sector=Financials" | jq '.macro_bias_score'
```

**Pass Criteria:**
- [ ] Scores are different (or very close but sector_weights differ)
- [ ] Both return valid numeric scores

---

## Test Case 2: MacroOverlay Component - Full Display Mode

### 2.1 Create a test page to view the component

Create a temporary test file at `frontend/src/pages/MacroOverlayTest.jsx`:

```jsx
import { MacroOverlay } from '../components/command-center';

export default function MacroOverlayTest() {
  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <h1 className="text-2xl font-bold mb-8">MacroOverlay Component Test</h1>

      {/* Full Display Mode */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Full Display Mode (AAPL - Technology)</h2>
        <div className="max-w-md">
          <MacroOverlay
            symbol="AAPL"
            sector="Technology"
            compact={false}
          />
        </div>
      </section>

      {/* Full Display Mode - Different Sector */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Full Display Mode (JPM - Financials)</h2>
        <div className="max-w-md">
          <MacroOverlay
            symbol="JPM"
            sector="Financials"
            compact={false}
          />
        </div>
      </section>

      {/* Compact Display Mode */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Compact Display Mode</h2>
        <div className="flex items-center gap-4 p-4 bg-gray-800 rounded">
          <span className="text-gray-400">AAPL</span>
          <MacroOverlay
            symbol="AAPL"
            sector="Technology"
            compact={true}
          />
        </div>
      </section>

      {/* Multiple Compact for comparison */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Compact Mode - Multiple Tickers</h2>
        <div className="space-y-2">
          {['AAPL', 'MSFT', 'JPM', 'XOM'].map(symbol => (
            <div key={symbol} className="flex items-center gap-4 p-3 bg-gray-800 rounded">
              <span className="text-gray-400 w-16">{symbol}</span>
              <MacroOverlay symbol={symbol} compact={true} />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
```

### 2.2 Add temporary route

In `frontend/src/App.jsx`, temporarily add:
```jsx
import MacroOverlayTest from './pages/MacroOverlayTest';

// In Routes:
<Route path="/test-macro-overlay" element={<MacroOverlayTest />} />
```

### 2.3 Navigate to test page

**Steps:**
1. Open browser to: `http://localhost:5173/test-macro-overlay`

**Pass Criteria for Full Display Mode:**
- [ ] Component loads without errors
- [ ] Shows "Macro Overlay" header
- [ ] Shows confidence percentage (e.g., "70% conf")
- [ ] Shows staleness warning icon if data is stale
- [ ] **Macro Bias section displays:**
  - [ ] Bias label (Bullish/Neutral/Bearish)
  - [ ] Bias score in parentheses
  - [ ] Appropriate icon (📈/➖/📉)
  - [ ] Color-coded background (green/yellow/red tint)
- [ ] **Trade Compatibility section displays:**
  - [ ] Compatibility label (Favorable/Mixed/Unfavorable)
  - [ ] Appropriate icon (✓/~/⚠)
  - [ ] Color-coded background
- [ ] **Key Macro Drivers section displays:**
  - [ ] At least 1-2 human-readable driver strings
  - [ ] Example: "Liquidity: Mixed (↓ RRP, ↑ TGA)"
  - [ ] Example: "Fed Policy: Neutral"
- [ ] **Footer shows:**
  - [ ] Update timestamp
  - [ ] "Full Macro Intel →" link to /macro-intelligence
- [ ] **CRITICAL: Disclaimer text is visible:**
  - [ ] Text reads: "Macro context informs, but never gates, your trading decisions."
  - [ ] Text is styled as small, gray, italic

---

## Test Case 3: MacroOverlay Component - Compact Display Mode

**Visual verification on test page:**

**Pass Criteria for Compact Mode:**
- [ ] Shows only inline elements (no card/box)
- [ ] Displays bias icon (📈/➖/📉)
- [ ] Displays compatibility label (Favorable/Mixed/Unfavorable)
- [ ] Shows staleness warning (⚠️) if data is stale
- [ ] Shows macro headwind icon (🌬️) if macro_headwind is true
- [ ] No expanded details visible
- [ ] Fits inline with other row content

---

## Test Case 4: Expand/Collapse Details

**Steps:**
1. On full display mode component, click the expand button (▶)
2. Verify expanded details appear
3. Click again (▼) to collapse

**Pass Criteria:**
- [ ] Clicking ▶ expands to show detailed breakdown
- [ ] Expanded view shows:
  - [ ] Trade Readiness score
  - [ ] Liquidity regime (risk-on/transition/risk-off)
  - [ ] MRI score
  - [ ] Sector name
  - [ ] Compatibility Notes (reasons list)
- [ ] Clicking ▼ collapses back to summary view

---

## Test Case 5: Macro Headwind Flag Display

**Steps:**
To force a macro headwind condition, temporarily modify the test:
```bash
# Test with high readiness (risk-off) to trigger headwind
curl -s http://localhost:8000/api/v1/command-center/macro-intelligence/ticker/TEST/macro-overlay | jq '.macro_headwind'
```

**Alternative: Check component behavior**
If `macro_headwind` is true in the response:

**Pass Criteria:**
- [ ] Red warning box appears: "🌬️ Macro Headwind: Current conditions may create resistance"
- [ ] In compact mode, shows 🌬️ icon

---

## Test Case 6: Graceful Degradation

### 6.1 Test error handling

**Steps:**
1. Stop the backend server
2. Refresh the test page
3. Observe component behavior

**Pass Criteria:**
- [ ] Component shows "Macro data unavailable" message
- [ ] No JavaScript errors in console
- [ ] Page doesn't crash

### 6.2 Test with invalid symbol

**Steps:**
```bash
curl -s http://localhost:8000/api/v1/command-center/macro-intelligence/ticker/INVALID123/macro-overlay | jq .
```

**Pass Criteria:**
- [ ] Returns valid response (graceful degradation)
- [ ] `macro_bias` may be "unknown" but response is valid
- [ ] `trade_compatibility` defaults to "mixed" (not "blocked")

---

## Test Case 7: Disclaimer Visibility Check

**Steps:**
1. Open the full display MacroOverlay component
2. Scroll to bottom if needed

**Pass Criteria:**
- [ ] Disclaimer text is VISIBLE at the bottom of the component
- [ ] Text exactly reads: "Macro context informs, but never gates, your trading decisions."
- [ ] Text styling: small font (10px), gray color, italic
- [ ] Disclaimer is NOT hidden or truncated

**Screenshot verification point:** Take a screenshot showing the disclaimer text visible in the component.

---

## Test Case 8: Link Navigation

**Steps:**
1. Click "Full Macro Intel →" link in the component footer

**Pass Criteria:**
- [ ] Navigates to /macro-intelligence page
- [ ] No errors during navigation

---

## Test Summary Checklist

| Test | Status | Notes |
|------|--------|-------|
| 1.1 API returns valid response | ⬜ | |
| 1.2 Sector parameter works | ⬜ | |
| 1.3 Different sectors = different scores | ⬜ | |
| 2.3 Full display mode renders | ⬜ | |
| 2.3 Macro bias displays | ⬜ | |
| 2.3 Trade compatibility displays | ⬜ | |
| 2.3 Drivers display (human-readable) | ⬜ | |
| 2.3 **Disclaimer visible** | ⬜ | CRITICAL |
| 3 Compact mode works | ⬜ | |
| 4 Expand/collapse works | ⬜ | |
| 5 Macro headwind flag shows | ⬜ | |
| 6.1 Graceful error handling | ⬜ | |
| 6.2 Invalid symbol handled | ⬜ | |
| 8 Link navigation works | ⬜ | |

---

## Cleanup

After testing, remove:
1. `frontend/src/pages/MacroOverlayTest.jsx`
2. The test route from `frontend/src/App.jsx`
