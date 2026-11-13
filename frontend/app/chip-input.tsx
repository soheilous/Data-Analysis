import { Button, Chip, Stack, TextField } from '@mui/material';

type ChipInputProps = {
  label: string;
  hint: string;
  value: string;
  items: string[];
  prefix?: string;
  onChange: (value: string) => void;
  onAdd: () => void;
  onRemove: (item: string) => void;
};

export function ChipInput({
  label, hint, value, items, prefix = '', onChange, onAdd, onRemove,
}: ChipInputProps) {
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
        <TextField
          label={label}
          value={value}
          helperText={hint}
          onChange={event => onChange(event.target.value)}
          onKeyDown={event => {
            if (event.nativeEvent.isComposing || event.key !== 'Enter') return;
            event.preventDefault();
            onAdd();
          }}
        />
        <Button
          variant="outlined"
          aria-label={`افزودن به ${label}`}
          disabled={!value.trim()}
          onClick={onAdd}
          sx={{ whiteSpace: 'nowrap' }}
        >
          افزودن
        </Button>
      </Stack>
      {items.length > 0 && (
        <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 0.75 }}>
          {items.map(item => (
            <Chip key={item} label={prefix + item} onDelete={() => onRemove(item)} />
          ))}
        </Stack>
      )}
    </Stack>
  );
}
