import { clsx } from "clsx";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  action?: React.ReactNode;
}

export default function Card({ children, className, title, action }: CardProps) {
  return (
    <div className={clsx("card", className)}>
      {(title || action) && (
        <div className="flex items-center justify-between mb-3">
          {title && (
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
              {title}
            </h3>
          )}
          {action && <div>{action}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
