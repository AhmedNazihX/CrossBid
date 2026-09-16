Tabs: segmented control (Agents | Runs) with solid blue active segment, or underline tabs for in-card sections.

```jsx
<Tabs items={[{label:'Agents',value:'a'},{label:'Runs',value:'r'}]} value="r" onChange={setTab}/>
```

variant="underline" adds optional counts.
