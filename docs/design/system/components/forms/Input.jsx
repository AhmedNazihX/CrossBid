import React from 'react';
export function Input({label,hint,error,icon,size='md',style,inputStyle,...rest}){
  const [f,setF]=React.useState(false);
  const h=size==='sm'?32:size==='lg'?48:40;
  return <label style={{display:'flex',flexDirection:'column',gap:6,font:'var(--type-body)',...style}}>
    {label&&<span style={{font:'var(--weight-medium) 13px/1 var(--font-sans)',color:'var(--text-primary)'}}>{label}</span>}
    <span style={{display:'flex',alignItems:'center',gap:8,height:h,padding:'0 12px',borderRadius:'var(--radius-md)',background:'var(--surface-card)',
      border:`1px solid ${error?'var(--status-danger)':f?'var(--border-focus)':'var(--border-default)'}`,boxShadow:f?'var(--shadow-focus)':'var(--shadow-xs)',transition:'box-shadow var(--duration-fast)'}}>
      {icon&&<span style={{display:'inline-flex',width:16,height:16,color:'var(--text-muted)'}}>{icon}</span>}
      <input onFocus={()=>setF(true)} onBlur={()=>setF(false)} style={{all:'unset',flex:1,minWidth:0,font:`400 ${size==='lg'?15:14}px/1 var(--font-sans)`,color:'var(--text-primary)',...inputStyle}} {...rest}/></span>
    {(hint||error)&&<span style={{font:'var(--type-body-sm)',color:error?'var(--status-danger-text)':'var(--text-muted)'}}>{error||hint}</span>}</label>;
}
