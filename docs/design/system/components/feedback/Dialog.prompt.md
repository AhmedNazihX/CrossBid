Dialog: confirmation modal (e.g. "Confirm verdict") — 480px, 40% scrim, actions right-aligned.

```jsx
<Dialog open title="Confirm verdict" description="This marks the tender as Go. CrossBid will begin drafting." footer={<><Button variant="secondary">Cancel</Button><Button>Confirm verdict</Button></>}/>
```

Primary action last. Never auto-confirm.
