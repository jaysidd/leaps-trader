/**
 * Card component with dark mode support
 */
export default function Card({ children, title, className = '', ...props }) {
  return (
    <div
      className={`bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 border border-transparent dark:border-gray-700 transition-colors ${className}`}
      {...props}
    >
      {title && <h3 className="text-lg font-semibold mb-4 text-gray-800 dark:text-gray-200">{title}</h3>}
      {children}
    </div>
  );
}
