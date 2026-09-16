import React from 'react';
const T = {
  success:['--status-success','--status-success-bg','--status-success-text'],
  warning:['--status-warning','--status-warning-bg','--status-warning-text'],
  danger:['--status-danger','--status-danger-bg','--status-danger-text'],
  info:['--status-info','--status-info-bg','--status-info-text'],
  neutral:['--status-neutral','--status-neutral-bg','--status-neutral-text'],
  brand:['--cb-blue-500','--cb-blue-50','--cb-blue-700'],
};
export function Badge({tone='neutral',dot=true,icon,size='md',pill=true,children,style}){
  const [d,bg,fg]=T[tone]||T.neutral;
  return <span style={{display:'inline-flex',alignItems:'center',gap:6,padding:size==='sm'?'3px 8px':'5px 10px',borderRadius:pill?'var(--radius-pill)':'var(--radius-sm)',
    background:`var(${bg})`,color:`var(${fg})`,font:`var(--weight-medium) ${size==='sm'?11:12}px/1.2 var(--font-sans)`,whiteSpace:'nowrap',...style}}>
    {icon?<span style={{display:'inline-flex',width:14,height:14}}>{icon}</span>:dot&&<span style={{width:7,height:7,borderRadius:'50%',background:`var(${d})`,flex:'none'}}/>}{children}</span>;
}
