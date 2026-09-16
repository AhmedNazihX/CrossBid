import React from 'react';
export function Select({label,options=[],value,placeholder='Select…',onChange,size='md',style}){
  const [open,setOpen]=React.useState(false);
  const [v,setV]=React.useState(value); const cur=value??v;
  const sel=options.find(o=>o.value===cur);
  const h=size==='sm'?32:40;
  return <div style={{display:'flex',flexDirection:'column',gap:6,position:'relative',...style}}>
    {label&&<span style={{font:'var(--weight-medium) 13px/1 var(--font-sans)'}}>{label}</span>}
    <button onClick={()=>setOpen(o=>!o)} style={{display:'flex',alignItems:'center',gap:10,height:h,padding:'0 12px',borderRadius:'var(--radius-md)',border:'1px solid var(--border-default)',background:'var(--surface-card)',
      font:'var(--weight-medium) 14px/1 var(--font-sans)',color:sel?'var(--text-primary)':'var(--text-muted)',cursor:'pointer',boxShadow:'var(--shadow-xs)',minWidth:120,justifyContent:'space-between'}}>
      <span>{label&&sel?sel.label:sel?sel.label:placeholder}</span>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{color:'var(--text-muted)'}}><path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/></svg></button>
    {open&&<div style={{position:'absolute',top:'calc(100% + 4px)',left:0,minWidth:'100%',zIndex:40,background:'var(--surface-card)',border:'1px solid var(--border-default)',borderRadius:'var(--radius-md)',boxShadow:'var(--shadow-md)',padding:4}}>
      {options.map(o=><div key={o.value} onClick={()=>{setV(o.value);onChange&&onChange(o.value);setOpen(false)}} style={{padding:'8px 10px',borderRadius:'var(--radius-sm)',font:'400 14px/1.2 var(--font-sans)',cursor:'pointer',
        background:o.value===cur?'var(--surface-sunken)':'transparent'}} onMouseEnter={e=>e.currentTarget.style.background='var(--surface-hover)'} onMouseLeave={e=>e.currentTarget.style.background=o.value===cur?'var(--surface-sunken)':'transparent'}>{o.label}</div>)}</div>}</div>;
}
