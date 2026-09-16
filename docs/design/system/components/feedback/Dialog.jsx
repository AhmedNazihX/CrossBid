import React from 'react';
export function Dialog({open,onClose,title,description,children,footer,width=480}){
  if(!open) return null;
  return <div onClick={onClose} style={{position:'fixed',inset:0,background:'var(--overlay-scrim)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:100,padding:24}}>
    <div role="dialog" onClick={e=>e.stopPropagation()} style={{width:'100%',maxWidth:width,background:'var(--surface-card)',border:'1px solid var(--border-default)',borderRadius:'var(--radius-xl)',boxShadow:'var(--shadow-lg)',padding:24,display:'flex',flexDirection:'column',gap:16}}>
      <div style={{display:'flex',alignItems:'flex-start',gap:12}}><div style={{flex:1}}><div style={{font:'var(--type-h4)',letterSpacing:'var(--tracking-tight)'}}>{title}</div>{description&&<div style={{font:'var(--type-body)',color:'var(--text-secondary)',marginTop:6}}>{description}</div>}</div>
        <button onClick={onClose} aria-label="Close" style={{all:'unset',cursor:'pointer',width:28,height:28,display:'inline-flex',alignItems:'center',justifyContent:'center',borderRadius:6,color:'var(--text-muted)',fontSize:18,lineHeight:1}}>×</button></div>
      {children}
      {footer&&<div style={{display:'flex',justifyContent:'flex-end',gap:8,paddingTop:8}}>{footer}</div>}</div></div>;
}
