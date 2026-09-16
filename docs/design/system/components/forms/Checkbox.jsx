import React from 'react';
export function Checkbox({label,checked,defaultChecked,onChange,disabled,description}){
  const [c,setC]=React.useState(!!defaultChecked); const cur=checked??c;
  return <label style={{display:'flex',gap:10,alignItems:'flex-start',cursor:disabled?'not-allowed':'pointer',opacity:disabled?.5:1,font:'var(--type-body)'}}>
    <span onClick={()=>{if(disabled)return;setC(!cur);onChange&&onChange(!cur)}} style={{width:18,height:18,flex:'none',marginTop:1,borderRadius:'var(--radius-xs)',border:`1px solid ${cur?'var(--cb-blue-500)':'var(--border-strong)'}`,background:cur?'var(--cb-blue-500)':'var(--surface-card)',display:'inline-flex',alignItems:'center',justifyContent:'center',transition:'background var(--duration-fast)'}}>
      {cur&&<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg>}</span>
    <span><span style={{display:'block',fontWeight:500,lineHeight:'20px'}}>{label}</span>{description&&<span style={{display:'block',font:'var(--type-body-sm)',color:'var(--text-muted)'}}>{description}</span>}</span></label>;
}
