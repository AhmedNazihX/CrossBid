import React from 'react';
const M={go:['Go','--verdict-go'],nogo:['No-go','--verdict-nogo'],conditional:['Conditional','--verdict-conditional'],insufficient:['Insufficient evidence','--verdict-insufficient']};
export function VerdictChip({verdict='insufficient',size='md',confirmed,style}){
  const [l,v]=M[verdict]||M.insufficient;
  return <span style={{display:'inline-flex',alignItems:'center',gap:8,padding:size==='lg'?'10px 14px':size==='sm'?'4px 8px':'7px 12px',borderRadius:'var(--radius-md)',background:`var(${v}-bg)`,color:`var(${v}-text)`,font:`600 ${size==='lg'?16:size==='sm'?12:14}px/1 var(--font-sans)`,whiteSpace:'nowrap',...style}}>
    <span style={{width:8,height:8,borderRadius:'50%',background:`var(${v})`}}/>{l}{confirmed&&<span style={{fontWeight:400,opacity:.8}}>· confirmed</span>}</span>;
}
