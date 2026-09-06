export function BrandMark({ className = '' }: { className?: string }) {
  return <img className={`paiban-mark ${className}`.trim()} src="/paiban-mark.svg" alt="" aria-hidden="true" draggable={false} />;
}
