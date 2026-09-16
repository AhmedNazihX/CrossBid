import React from 'react';
const V = {
  primary:{bg:'var(--surface-brand)',hover:'var(--cb-blue-600)',color:'var(--text-inverse)',border:'transparent'},
  secondary:{bg:'var(--surface-card)',hover:'var(--surface-hover)',color:'var(--text-primary)',border:'var(--border-default)'},
  ghost:{bg:'transparent',hover:'var(--surface-hover)',color:'var(--text-primary)',border:'transparent'},
  inverse:{bg:'var(--surface-inverse)',hover:'var(--cb-stone-800)',color:'var(--text-inverse)',border:'transparent'},
  danger:{bg:'var(--status-danger)',hover:'var(--status-danger-text)',color:'var(--text-inverse)',border:'transparent'},
};
const S = {sm:{h:'var(--control-sm)',px:12,fs:13,gap:6},md:{h:'var(--control-md)',px:16,fs:14,gap:8},lg:{h:'var(--control-lg)',px:20,fs:15,gap:8}};
export function Button({variant='primary',size='md',icon,iconRight,children,disabled,fullWidth,style,...rest}){
  const [hov,setHov]=React.useState(false);
  const v=V[variant]||V.primary, s=S[size]||S.md;
  return <button disabled={disabled} onMouseEnter={()=>setHov(true)} onMouseLeave={()=>setHov(false)} style={{
    display:fullWidth?'flex':'inline-flex',width:fullWidth?'100%':undefined,alignItems:'center',justifyContent:'center',gap:s.gap,
    height:s.h,padding:`0 ${s.px}px`,borderRadius:'var(--radius-md)',border:`1px solid ${v.border}`,
    background:hov&&!disabled?v.hover:v.bg,color:v.color,font:`var(--weight-medium) ${s.fs}px/1 var(--font-sans)`,
    cursor:disabled?'not-allowed':'pointer',opacity:disabled?.5:1,transition:'background var(--duration-fast) var(--ease-standard)',
    boxShadow:variant==='secondary'?'var(--shadow-xs)':'none',whiteSpace:'nowrap',...style}} {...rest}>
    {icon&&<span style={{display:'inline-flex',width:16,height:16}}>{icon}</span>}{children}{iconRight&&<span style={{display:'inline-flex',width:16,height:16}}>{iconRight}</span>}
  </button>;
}
