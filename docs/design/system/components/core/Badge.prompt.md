Badge: status chip (Succeeded, Needs attention, Failed, In progress, Identification…) — tinted 50 bg, 700 text, 7px dot.

```jsx
<Badge tone="success" icon={<CheckCircleIcon/>}>Succeeded</Badge>
<Badge tone="info" pill={false}>Identification</Badge>
```

Tones map to status tokens. `pill={false}` gives the 6px-radius phase chip used in tables.
