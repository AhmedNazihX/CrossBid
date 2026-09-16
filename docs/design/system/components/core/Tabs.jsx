import React from 'react';
export function Tabs({items,value,onChange,variant='segmented',style}){
  const [v,setV]=React.useState(value??items[0]?.value);
  const cur=value??v; const set=x=>{setV(x);onChange&&onChange(x)};
  if(variant==='underline') return <div role="tablist" style={{display:'flex',gap:24,borderBottom:'1px solid var(--border-default)',...style}}>
    {items.map(it=><button key={it.value} role="tab" onClick={()=>set(it.value)} style={{all:'unset',cursor:'pointer',padding:'10px 0',marginBottom:-1,font:'var(--weight-medium) 14px/1 var(--font-sans)',
      color:cur===it.value?'var(--text-primary)':'var(--text-muted)',borderBottom:`2px solid ${cur===it.value?'var(--cb-blue-500)':'transparent'}`}}>{it.label}{it.count!=null&&<span style={{marginLeft:6,color:'var(--text-muted)',fontWeight:400}}>{it.count}</span>}</button>)}</div>;
  return <div role="tablist" style={{display:'inline-flex',border:'1px solid var(--border-default)',borderRadius:'var(--radius-md)',background:'var(--surface-card)',overflow:'hidden',...style}}>
    {items.map(it=><button key={it.value} role="tab" onClick={()=>set(it.value)} style={{all:'unset',cursor:'pointer',height:38,padding:'0 18px',font:'var(--weight-medium) 14px/1 var(--font-sans)',
      background:cur===it.value?'var(--surface-brand)':'transparent',color:cur===it.value?'#fff':'var(--text-primary)',transition:'background var(--duration-fast)'}}>{it.label}</button>)}</div>;
}
