import React from 'react';
const T={success:'--status-success',warning:'--status-warning',danger:'--status-danger',info:'--status-info'};
export function Toast({tone='info',title,description,action,onDismiss,style}){
  return <div role="status" style={{display:'flex',gap:12,alignItems:'flex-start',width:360,padding:'12px 14px',background:'var(--surface-card)',border:'1px solid var(--border-default)',borderRadius:'var(--radius-lg)',boxShadow:'var(--shadow-md)',...style}}>
    <span style={{width:8,height:8,borderRadius:'50%',background:`var(${T[tone]||T.info})`,marginTop:6,flex:'none'}}/>
    <div style={{flex:1,minWidth:0}}><div style={{font:'var(--weight-medium) 14px/1.3 var(--font-sans)'}}>{title}</div>{description&&<div style={{font:'var(--type-body-sm)',color:'var(--text-secondary)',marginTop:2}}>{description}</div>}
      {action&&<div style={{marginTop:8}}>{action}</div>}</div>
    {onDismiss&&<button onClick={onDismiss} aria-label="Dismiss" style={{all:'unset',cursor:'pointer',color:'var(--text-muted)',fontSize:16,lineHeight:1}}>×</button>}</div>;
}
