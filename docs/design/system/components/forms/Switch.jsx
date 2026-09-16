import React from 'react';
export function Switch({label,checked,defaultChecked,onChange,disabled,size='md'}){
  const [c,setC]=React.useState(!!defaultChecked); const cur=checked??c;
  const w=size==='sm'?32:40,h=size==='sm'?18:22,k=h-4;
  return <label style={{display:'inline-flex',alignItems:'center',gap:10,cursor:disabled?'not-allowed':'pointer',opacity:disabled?.5:1,font:'var(--type-body)'}}>
    <span role="switch" aria-checked={cur} onClick={()=>{if(disabled)return;setC(!cur);onChange&&onChange(!cur)}} style={{width:w,height:h,borderRadius:999,background:cur?'var(--cb-blue-500)':'var(--cb-stone-300)',position:'relative',transition:'background var(--duration-base) var(--ease-standard)',flex:'none'}}>
      <span style={{position:'absolute',top:2,left:cur?w-k-2:2,width:k,height:k,borderRadius:'50%',background:'#fff',boxShadow:'var(--shadow-sm)',transition:'left var(--duration-base) var(--ease-standard)'}}/></span>
    {label&&<span style={{fontWeight:500}}>{label}</span>}</label>;
}
