const {NavItem,Button,IconButton}=window.CrossBidDesignSystem_b81312;
function Sidebar({route,go}){
  const Eye=({c})=><div style={{font:'500 12px/1 var(--font-sans)',letterSpacing:'.06em',color:'var(--text-muted)',padding:'0 10px',margin:'24px 0 10px'}}>{c}</div>;
  return <aside style={{width:'var(--sidebar-width)',flex:'none',padding:'28px 20px',display:'flex',flexDirection:'column',height:'100vh',position:'sticky',top:0,boxSizing:'border-box'}}>
    <div style={{display:'flex',alignItems:'center',padding:'4px 8px'}}><img src="../../assets/logo-lockup.png" alt="CrossBid" style={{height:30,display:'block'}}/></div>
    <Eye c="WORKFLOW"/>
    <div style={{display:'flex',flexDirection:'column',gap:4}}>
      <NavItem icon={<Icons.grid/>} label="Dashboard" active={route==='dashboard'} onClick={()=>go('dashboard')}/>
      <NavItem icon={<Icons.file/>} label="Tenders" active={route==='tenders'} onClick={()=>go('matrix')}/>
      <NavItem icon={<Icons.fileCheck/>} label="Compliance" active={route==='matrix'} onClick={()=>go('matrix')}/>
      <NavItem icon={<Icons.layers/>} label="Certificates" onClick={()=>go('matrix')}/>
      <NavItem icon={<Icons.shield/>} label="Verdicts" active={route==='verdict'} tone="solid" onClick={()=>go('verdict')}/>
    </div>
    <div style={{height:1,background:'var(--border-default)',margin:'24px 0 0'}}/>
    <Eye c="PLATFORM"/>
    <div style={{display:'flex',flexDirection:'column',gap:4}}>
      <NavItem icon={<Icons.spark/>} label="Agent runs" active={route==='runs'} onClick={()=>go('runs')}/>
      <NavItem icon={<Icons.db/>} label="Company profile" trailing={<Icons.chev size={16}/>}/>
      <NavItem icon={<Icons.chart/>} label="Reports"/>
    </div>
    <div style={{flex:1}}/>
    <div style={{display:'flex',alignItems:'center',gap:10,padding:'10px'}}><span style={{width:32,height:32,borderRadius:'50%',background:'var(--cb-stone-200)',display:'inline-flex',alignItems:'center',justifyContent:'center',font:'600 12px/1 var(--font-sans)',color:'var(--text-secondary)'}}>LH</span><div><div style={{font:'500 14px/1.2 var(--font-sans)'}}>Lena Hartmann</div><div style={{font:'400 12px/1.2 var(--font-sans)',color:'var(--text-muted)'}}>Nordvik Elektro GmbH</div></div></div>
  </aside>;
}
function Frame({children}){return <main style={{flex:1,minWidth:0,padding:'28px 28px 28px 0'}}><div style={{background:'var(--surface-card)',border:'1px solid var(--border-default)',borderRadius:14,minHeight:'calc(100vh - 56px)',padding:32,boxShadow:'var(--shadow-xs)'}}>{children}</div></main>}
function PageHeader({title,children}){return <div style={{display:'flex',alignItems:'center',gap:12,marginBottom:24}}><h1 style={{font:'600 30px/1.1 var(--font-sans)',letterSpacing:'-0.03em',margin:0,flex:1}}>{title}</h1>{children}</div>}
function SectionHead({title,link}){return <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',margin:'28px 0 14px'}}><div style={{font:'600 18px/1.2 var(--font-sans)',letterSpacing:'-0.02em'}}>{title}</div>{link&&<a href="#" style={{font:'500 14px/1 var(--font-sans)',color:'var(--text-secondary)',display:'inline-flex',gap:6,alignItems:'center'}}>{link} <Icons.arrow size={14}/></a>}</div>}
Object.assign(window,{Sidebar,Frame,PageHeader,SectionHead});