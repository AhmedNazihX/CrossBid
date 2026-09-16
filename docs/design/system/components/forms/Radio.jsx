import React from 'react';
export function Radio({options,value,onChange,name,direction='column'}){
  const [v,setV]=React.useState(value); const cur=value??v;
  return <div role="radiogroup" style={{display:'flex',flexDirection:direction,gap:direction==='row'?20:10}}>
    {options.map(o=>{const on=cur===o.value;return <label key={o.value} onClick={()=>{setV(o.value);onChange&&onChange(o.value)}} style={{display:'flex',gap:10,alignItems:'flex-start',cursor:'pointer',font:'var(--type-body)'}}>
      <span style={{width:18,height:18,flex:'none',marginTop:1,borderRadius:'50%',border:`${on?5:1}px solid ${on?'var(--cb-blue-500)':'var(--border-strong)'}`,background:'#fff',transition:'border var(--duration-fast)'}}/>
      <span><span style={{display:'block',fontWeight:500,lineHeight:'20px'}}>{o.label}</span>{o.description&&<span style={{display:'block',font:'var(--type-body-sm)',color:'var(--text-muted)'}}>{o.description}</span>}</span></label>})}</div>;
}
