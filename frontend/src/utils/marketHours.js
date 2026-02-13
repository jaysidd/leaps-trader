/**
 * Market Hours Utility
 *
 * Determines if the US stock market is currently open.
 * Used to control auto-refresh behavior.
 */

// US Market holidays for 2024-2026 (NYSE/NASDAQ)
// Format: 'YYYY-MM-DD'
const US_MARKET_HOLIDAYS = [
  // 2024
  '2024-01-01', // New Year's Day
  '2024-01-15', // MLK Day
  '2024-02-19', // Presidents Day
  '2024-03-29', // Good Friday
  '2024-05-27', // Memorial Day
  '2024-06-19', // Juneteenth
  '2024-07-04', // Independence Day
  '2024-09-02', // Labor Day
  '2024-11-28', // Thanksgiving
  '2024-12-25', // Christmas

  // 2025
  '2025-01-01', // New Year's Day
  '2025-01-20', // MLK Day
  '2025-02-17', // Presidents Day
  '2025-04-18', // Good Friday
  '2025-05-26', // Memorial Day
  '2025-06-19', // Juneteenth
  '2025-07-04', // Independence Day
  '2025-09-01', // Labor Day
  '2025-11-27', // Thanksgiving
  '2025-12-25', // Christmas

  // 2026
  '2026-01-01', // New Year's Day
  '2026-01-19', // MLK Day
  '2026-02-16', // Presidents Day
  '2026-04-03', // Good Friday
  '2026-05-25', // Memorial Day
  '2026-06-19', // Juneteenth
  '2026-07-03', // Independence Day (observed)
  '2026-09-07', // Labor Day
  '2026-11-26', // Thanksgiving
  '2026-12-25', // Christmas
];

// Early close days (1:00 PM ET)
const EARLY_CLOSE_DAYS = [
  '2024-07-03',  // Day before Independence Day
  '2024-11-29',  // Day after Thanksgiving
  '2024-12-24',  // Christmas Eve
  '2025-07-03',
  '2025-11-28',
  '2025-12-24',
  '2026-11-27',
  '2026-12-24',
];

/**
 * Get current time in Eastern Time
 */
export function getEasternTime() {
  const now = new Date();
  // Convert to Eastern Time
  const etString = now.toLocaleString('en-US', {
    timeZone: 'America/New_York'
  });
  return new Date(etString);
}

/**
 * Get today's date in YYYY-MM-DD format (Eastern Time)
 */
export function getTodayET() {
  const et = getEasternTime();
  return et.toISOString().split('T')[0];
}

/**
 * Check if today is a weekend
 */
export function isWeekend() {
  const et = getEasternTime();
  const day = et.getDay();
  return day === 0 || day === 6; // Sunday = 0, Saturday = 6
}

/**
 * Check if today is a US market holiday
 */
export function isMarketHoliday() {
  const today = getTodayET();
  return US_MARKET_HOLIDAYS.includes(today);
}

/**
 * Check if today is an early close day
 */
export function isEarlyCloseDay() {
  const today = getTodayET();
  return EARLY_CLOSE_DAYS.includes(today);
}

/**
 * Check if market is currently within trading hours
 * Regular hours: 9:30 AM - 4:00 PM ET
 * Early close: 9:30 AM - 1:00 PM ET
 */
export function isDuringTradingHours() {
  const et = getEasternTime();
  const hours = et.getHours();
  const minutes = et.getMinutes();
  const timeInMinutes = hours * 60 + minutes;

  const marketOpen = 9 * 60 + 30;  // 9:30 AM = 570 minutes
  const regularClose = 16 * 60;     // 4:00 PM = 960 minutes
  const earlyClose = 13 * 60;       // 1:00 PM = 780 minutes

  const closeTime = isEarlyCloseDay() ? earlyClose : regularClose;

  return timeInMinutes >= marketOpen && timeInMinutes < closeTime;
}

/**
 * Check if market is currently open
 * Returns true only if:
 * - It's a weekday
 * - It's not a holiday
 * - Current time is within trading hours
 */
export function isMarketOpen() {
  if (isWeekend()) return false;
  if (isMarketHoliday()) return false;
  return isDuringTradingHours();
}

/**
 * Get market status with details
 */
export function getMarketStatus() {
  const et = getEasternTime();

  if (isWeekend()) {
    return {
      isOpen: false,
      reason: 'weekend',
      message: 'Market closed (Weekend)',
      nextOpen: getNextMarketOpen()
    };
  }

  if (isMarketHoliday()) {
    return {
      isOpen: false,
      reason: 'holiday',
      message: 'Market closed (Holiday)',
      nextOpen: getNextMarketOpen()
    };
  }

  const hours = et.getHours();
  const minutes = et.getMinutes();
  const timeInMinutes = hours * 60 + minutes;

  const marketOpen = 9 * 60 + 30;
  const regularClose = 16 * 60;
  const earlyClose = 13 * 60;
  const closeTime = isEarlyCloseDay() ? earlyClose : regularClose;

  if (timeInMinutes < marketOpen) {
    return {
      isOpen: false,
      reason: 'pre-market',
      message: 'Market opens at 9:30 AM ET',
      opensIn: marketOpen - timeInMinutes
    };
  }

  if (timeInMinutes >= closeTime) {
    return {
      isOpen: false,
      reason: 'after-hours',
      message: 'Market closed for the day',
      nextOpen: getNextMarketOpen()
    };
  }

  return {
    isOpen: true,
    reason: 'trading',
    message: isEarlyCloseDay() ? 'Market open (Early close 1PM)' : 'Market open',
    closesIn: closeTime - timeInMinutes
  };
}

/**
 * Get next market open time (simplified - returns next weekday 9:30 AM ET)
 */
export function getNextMarketOpen() {
  const et = getEasternTime();
  let next = new Date(et);

  // If it's before market open today, return today
  const hours = next.getHours();
  const minutes = next.getMinutes();
  if (hours < 9 || (hours === 9 && minutes < 30)) {
    if (!isWeekend() && !isMarketHoliday()) {
      next.setHours(9, 30, 0, 0);
      return next;
    }
  }

  // Move to next day
  next.setDate(next.getDate() + 1);
  next.setHours(9, 30, 0, 0);

  // Skip weekends
  while (next.getDay() === 0 || next.getDay() === 6) {
    next.setDate(next.getDate() + 1);
  }

  // Note: This doesn't skip holidays, would need more complex logic

  return next;
}

/**
 * Calculate optimal refresh interval based on market status
 * - During market hours: 5 minutes
 * - Pre-market (within 1 hour of open): 5 minutes
 * - Otherwise: 30 minutes (or disable)
 */
export function getRefreshInterval() {
  const status = getMarketStatus();

  if (status.isOpen) {
    return 5 * 60 * 1000; // 5 minutes during market hours
  }

  if (status.reason === 'pre-market' && status.opensIn <= 60) {
    return 5 * 60 * 1000; // 5 minutes if within 1 hour of open
  }

  // Market is closed - use longer interval or disable
  return 30 * 60 * 1000; // 30 minutes when closed
}

/**
 * Should we refresh data?
 * Returns true during market hours or within 1 hour of market open
 */
export function shouldAutoRefresh() {
  const status = getMarketStatus();

  if (status.isOpen) return true;

  // Also refresh during pre-market if within 1 hour of open
  if (status.reason === 'pre-market' && status.opensIn <= 60) {
    return true;
  }

  return false;
}

export default {
  isMarketOpen,
  isWeekend,
  isMarketHoliday,
  isDuringTradingHours,
  getMarketStatus,
  getRefreshInterval,
  shouldAutoRefresh,
  getEasternTime
};
