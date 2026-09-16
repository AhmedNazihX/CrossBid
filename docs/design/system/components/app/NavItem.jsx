import React from 'react';
export function NavItem({icon,label,active,tone='soft',trailing,onClick}){
  const [hov,setHov]=React.useState(false);
  const solid=tone==='solid';
  return <button onClick={onClick} onMouseEnter={()=>setHov(true)} onMouseLeave={()=>setHov(false)} style={{all:'unset',display:'flex',alignItems:'center',gap:12,width:'100%',boxSizing:'border-box',height:44,padding:'0 10px',borderRadius:'var(--radius-md)',cursor:'pointer',
    background:active?'var(--surface-card)':hov?'var(--surface-hover)':'transparent',border:`1px solid ${active?'var(--border-default)':'transparent'}`,boxShadow:active?'var(--shadow-active-nav)':'none',transition:'background var(--duration-fast)'}}>
    <span style={{width:32,height:32,borderRadius:10,display:'inline-flex',alignItems:'center',justifyContent:'center',background:solid?'var(--surface-accent)':'var(--cb-blue-100)',color:solid?'#fff':'var(--cb-blue-500)',flex:'none'}}><span style={{display:'inline-flex',width:18,height:18}}>{icon}</span></span>
    <span style={{font:'var(--weight-medium) 15px/1 var(--font-sans)',color:'var(--text-primary)',flex:1}}>{label}</span>
    {trailing&&<span style={{color:'var(--text-muted)',display:'inline-flex'}}>{trailing}</span>}</button>;
}
