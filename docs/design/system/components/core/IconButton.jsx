import React from 'react';
export function IconButton({variant='secondary',size='md',label,children,disabled,active,style,...rest}){
  const [hov,setHov]=React.useState(false);
  const d=size==='sm'?32:size==='lg'?48:40;
  const bg=active?'var(--surface-brand-soft)':hov&&!disabled?'var(--surface-hover)':variant==='ghost'?'transparent':'var(--surface-card)';
  return <button aria-label={label} title={label} disabled={disabled} onMouseEnter={()=>setHov(true)} onMouseLeave={()=>setHov(false)} style={{
    width:d,height:d,display:'inline-flex',alignItems:'center',justifyContent:'center',borderRadius:'var(--radius-md)',
    border:variant==='ghost'?'1px solid transparent':'1px solid var(--border-default)',background:bg,color:active?'var(--text-brand)':'var(--text-primary)',
    cursor:disabled?'not-allowed':'pointer',opacity:disabled?.5:1,transition:'background var(--duration-fast)',...style}} {...rest}>
    <span style={{display:'inline-flex',width:size==='sm'?16:18,height:size==='sm'?16:18}}>{children}</span></button>;
}
