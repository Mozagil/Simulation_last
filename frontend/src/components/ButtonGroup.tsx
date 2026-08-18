interface ButtonGroupItem {
  key: string;
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}

interface ButtonGroupProps {
  title: string;
  items: ButtonGroupItem[];
  emptyLabel?: string;
}

/** Başlıklı, yatay bir buton grubu — seçim modu, işlemler, dinamik gruplar
 * gibi birden fazla buton kümesi için tek tip görsel dil sağlar. */
function ButtonGroup({ title, items, emptyLabel }: ButtonGroupProps) {
  return (
    <div className="button-group">
      <span className="button-group-title">{title}</span>
      <div className="button-group-row">
        {items.length === 0 && emptyLabel ? (
          <span className="button-group-empty">{emptyLabel}</span>
        ) : (
          items.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`button-group-button${item.active ? " active" : ""}`}
              disabled={item.disabled}
              onClick={item.onClick}
              title={item.label}
            >
              {item.label}
            </button>
          ))
        )}
      </div>
    </div>
  );
}

export default ButtonGroup;
