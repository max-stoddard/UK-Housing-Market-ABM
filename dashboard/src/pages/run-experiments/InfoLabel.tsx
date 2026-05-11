// Author: Max Stoddard
interface InfoLabelProps {
  label: string;
  info: string;
}

export function InfoLabel({ label, info }: InfoLabelProps) {
  return (
    <span className="setting-field-label">
      <span>{label}</span>
      <span className="setting-info-trigger" tabIndex={0} aria-label={`${label} information`}>
        <span aria-hidden="true" className="setting-info-icon">
          i
        </span>
        <span role="tooltip" className="setting-info-tooltip">
          {info}
        </span>
      </span>
    </span>
  );
}
