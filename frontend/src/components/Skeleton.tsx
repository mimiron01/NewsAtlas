interface SkeletonProps {
  rows?: number;
}

export default function Skeleton({ rows = 3 }: SkeletonProps) {
  return (
    <div className="skeleton-group" aria-hidden="true">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton-row" />
      ))}
    </div>
  );
}
