import React from 'react';
export function MetricCard({label,value,delta,deltaTone='success',period,style}){
  const c=deltaTone==='success'?'var(--status-success-text)':deltaTone==='danger'?'var(--status-danger-text)':'var(--text-muted)';
  return <div style={{background:'var(--surface-card)',border:'1px solid var(--border-default)',borderRadius:'var(--radius-lg)',padding:24,boxShadow:'var(--shadow-xs)',...style}}>
    <div style={{font:'var(--type-body)',color:'var(--text-secondary)'}}>{label}</div>
    <div style={{font:'600 32px/1.1 var(--font-sans)',letterSpacing:'var(--tracking-tight)',marginTop:8}}>{value}</div>
    {(delta||period)&&<div style={{display:'flex',gap:8,font:'var(--type-body-sm)',marginTop:10}}>{delta&&<span style={{color:c,fontWeight:500}}>{delta}</span>}{period&&<span style={{color:'var(--text-muted)'}}>{period}</span>}</div>}</div>;
}
