import React from 'react';
import { Badge } from '../core/Badge.jsx';
import { Button } from '../core/Button.jsx';
export function RunCard({title,summary,status='success',statusLabel,meta=[],actionLabel='View run',onAction,style}){
  const labels={success:'Succeeded',warning:'Needs attention',danger:'Failed',info:'In progress',neutral:'Queued'};
  return <div style={{background:'var(--surface-card)',border:'1px solid var(--border-default)',borderRadius:'var(--radius-lg)',padding:24,boxShadow:'var(--shadow-xs)',display:'flex',flexDirection:'column',gap:14,...style}}>
    <div style={{display:'flex',alignItems:'center',gap:16}}><div style={{font:'var(--type-h4)',letterSpacing:'var(--tracking-tight)',flex:1}}>{title}</div>
      <Button variant="secondary" size="sm" onClick={onAction} icon={<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>}>{actionLabel}</Button></div>
    {summary&&<div style={{font:'var(--type-body)',color:'var(--text-secondary)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{summary}</div>}
    <div style={{display:'flex',alignItems:'center',gap:20,flexWrap:'wrap'}}><Badge tone={status}>{statusLabel||labels[status]}</Badge>
      {meta.map((m,i)=><span key={i} style={{display:'inline-flex',alignItems:'center',gap:6,font:'var(--type-body)',color:'var(--text-secondary)'}}>{m.icon&&<span style={{display:'inline-flex',width:16,height:16,color:'var(--text-muted)'}}>{m.icon}</span>}{m.label}</span>)}</div></div>;
}
