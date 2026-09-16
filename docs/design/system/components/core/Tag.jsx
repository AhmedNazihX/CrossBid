import React from 'react';
export function Tag({children,onRemove,mono,style}){
  return <span style={{display:'inline-flex',alignItems:'center',gap:6,padding:'4px 8px',borderRadius:'var(--radius-sm)',border:'1px solid var(--border-default)',background:'var(--surface-sunken)',
    color:'var(--text-secondary)',font:mono?'var(--type-mono)':'var(--weight-medium) 12px/1.2 var(--font-sans)',...style}}>{children}
    {onRemove&&<button onClick={onRemove} aria-label="Remove" style={{all:'unset',cursor:'pointer',lineHeight:1,color:'var(--text-muted)',fontSize:13}}>×</button>}</span>;
}
