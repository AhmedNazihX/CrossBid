import React from 'react';
export function Card({title,icon,actions,padding=24,children,hoverable,style,onClick}){
  const [hov,setHov]=React.useState(false);
  return <div onClick={onClick} onMouseEnter={()=>setHov(true)} onMouseLeave={()=>setHov(false)} style={{background:'var(--surface-card)',border:'1px solid var(--border-default)',borderRadius:'var(--radius-lg)',
    boxShadow:hoverable&&hov?'var(--shadow-sm)':'var(--shadow-xs)',padding,cursor:onClick?'pointer':undefined,transition:'box-shadow var(--duration-fast)',...style}}>
    {(title||actions)&&<div style={{display:'flex',alignItems:'center',gap:10,marginBottom:children?16:0}}>
      {icon&&<span style={{display:'inline-flex',width:20,height:20,color:'var(--text-primary)'}}>{icon}</span>}
      {title&&<div style={{font:'var(--type-h4)',letterSpacing:'var(--tracking-tight)',flex:1}}>{title}</div>}
      {actions&&<div style={{display:'flex',gap:8,alignItems:'center'}}>{actions}</div>}</div>}
    {children}</div>;
}
