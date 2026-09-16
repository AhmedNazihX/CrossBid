import React from 'react';
export function Tooltip({content,children,side='top'}){
  const [open,setOpen]=React.useState(false);
  const pos=side==='bottom'?{top:'calc(100% + 6px)'}:{bottom:'calc(100% + 6px)'};
  return <span style={{position:'relative',display:'inline-flex'}} onMouseEnter={()=>setOpen(true)} onMouseLeave={()=>setOpen(false)}>{children}
    {open&&<span role="tooltip" style={{position:'absolute',left:'50%',transform:'translateX(-50%)',...pos,zIndex:50,background:'var(--surface-inverse)',color:'#fff',padding:'6px 10px',borderRadius:'var(--radius-sm)',
      font:'var(--weight-medium) 12px/1.3 var(--font-sans)',whiteSpace:'nowrap',boxShadow:'var(--shadow-md)'}}>{content}</span>}</span>;
}
