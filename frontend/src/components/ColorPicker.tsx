import { COLOR_NAMES, PALETTE } from '../palette'

interface ColorPickerProps {
  value: string | null
  onChange: (color: string) => void
}

export function ColorPicker({ value, onChange }: ColorPickerProps) {
  return (
    <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Color">
      {COLOR_NAMES.map((name) => {
        const isSelected = name === value
        return (
          <button
            key={name}
            type="button"
            role="radio"
            aria-checked={isSelected}
            aria-label={name}
            title={name}
            onClick={() => !isSelected && onChange(name)}
            style={{ backgroundColor: PALETTE[name].accent }}
            className={`h-7 w-7 rounded-full transition-transform hover:scale-110 ${
              isSelected ? 'ring-2 ring-white ring-offset-2 ring-offset-black/40' : ''
            }`}
          />
        )
      })}
    </div>
  )
}
