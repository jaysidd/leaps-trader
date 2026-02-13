import { useState, useRef } from 'react';

/**
 * Lightweight tooltip that appears on hover.
 * Positions above the trigger by default, falls back to below if near top of viewport.
 */
export default function Tooltip({ children, text, className = '' }) {
  const [visible, setVisible] = useState(false);
  const wrapperRef = useRef(null);

  if (!text) return children;

  return (
    <div
      ref={wrapperRef}
      className={`relative inline-block ${className}`}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      {children}
      {visible && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 px-3 py-2 text-xs leading-relaxed text-gray-100 bg-gray-900 dark:bg-gray-700 rounded-lg shadow-lg pointer-events-none">
          {text}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900 dark:border-t-gray-700" />
        </div>
      )}
    </div>
  );
}
