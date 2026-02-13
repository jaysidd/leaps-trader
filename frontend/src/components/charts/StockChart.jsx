/**
 * StockChart Component
 *
 * Displays an interactive TradingView chart for a stock symbol.
 * Features: Candlestick charts, technical indicators, drawing tools
 */
import { memo } from 'react';
import { AdvancedRealTimeChart } from 'react-ts-tradingview-widgets';

// Map Yahoo Finance exchange codes to TradingView exchange prefixes
const mapExchangeToTradingView = (yahooExchange) => {
  if (!yahooExchange) return 'NASDAQ';

  const exchangeMap = {
    // NASDAQ variants
    'NMS': 'NASDAQ',      // NASDAQ Global Select Market
    'NGM': 'NASDAQ',      // NASDAQ Global Market
    'NCM': 'NASDAQ',      // NASDAQ Capital Market
    'NASDAQ': 'NASDAQ',

    // NYSE variants
    'NYQ': 'NYSE',        // NYSE
    'NYSE': 'NYSE',
    'NYS': 'NYSE',
    'PCX': 'NYSE',        // NYSE Arca
    'ASE': 'AMEX',        // NYSE American (AMEX)
    'AMEX': 'AMEX',

    // Other US exchanges
    'BTS': 'NYSE',        // BATS -> use NYSE
    'BATS': 'NYSE',
  };

  return exchangeMap[yahooExchange.toUpperCase()] || 'NASDAQ';
};

const StockChart = memo(({
  symbol,
  exchange,
  theme = 'light',
  height = 500,
  interval = 'D',
  showToolbar = true,
  allowSymbolChange = false,
  className = ''
}) => {
  // Format symbol for TradingView (e.g., AAPL -> NASDAQ:AAPL)
  const formatSymbol = (sym) => {
    if (!sym) return 'NASDAQ:AAPL';
    // If already has exchange prefix, use as-is
    if (sym.includes(':')) return sym;
    // Use the exchange prop to determine correct prefix
    const tvExchange = mapExchangeToTradingView(exchange);
    return `${tvExchange}:${sym}`;
  };

  return (
    <div className={`w-full ${className}`} style={{ height }}>
      <AdvancedRealTimeChart
        symbol={formatSymbol(symbol)}
        theme={theme}
        autosize
        interval={interval}
        timezone="America/New_York"
        style="1" // Candlestick
        locale="en"
        toolbar_bg="#f1f3f6"
        enable_publishing={false}
        allow_symbol_change={allowSymbolChange}
        hide_top_toolbar={!showToolbar}
        hide_legend={false}
        save_image={false}
        container_id={`tradingview_${symbol}`}
        studies={[
          "MASimple@tv-basicstudies", // 50-day SMA
          "RSI@tv-basicstudies"       // RSI indicator
        ]}
        withdateranges={true}
        details={true}
        hotlist={false}
        calendar={false}
      />
    </div>
  );
});

StockChart.displayName = 'StockChart';

/**
 * Mini chart for quick price overview
 */
export const MiniChart = memo(({ symbol, exchange, theme = 'light', height = 220 }) => {
  const formatSymbol = (sym) => {
    if (!sym) return 'NASDAQ:AAPL';
    if (sym.includes(':')) return sym;
    const tvExchange = mapExchangeToTradingView(exchange);
    return `${tvExchange}:${sym}`;
  };

  return (
    <div className="w-full" style={{ height }}>
      <AdvancedRealTimeChart
        symbol={formatSymbol(symbol)}
        theme={theme}
        autosize
        interval="D"
        timezone="America/New_York"
        style="3" // Area chart
        locale="en"
        hide_top_toolbar={true}
        hide_legend={true}
        save_image={false}
        allow_symbol_change={false}
        container_id={`minichart_${symbol}`}
      />
    </div>
  );
});

MiniChart.displayName = 'MiniChart';

export default StockChart;
