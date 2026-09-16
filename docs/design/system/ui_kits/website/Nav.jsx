const {Button}=window.CrossBidDesignSystem_b81312;
function Nav(){return <header style={{position:'sticky',top:0,zIndex:50,background:'rgba(250,250,249,0.8)',backdropFilter:'var(--blur-glass)',WebkitBackdropFilter:'var(--blur-glass)',borderBottom:'1px solid var(--border-subtle)'}}>
  <div style={{maxWidth:'var(--marketing-max)',margin:'0 auto',padding:'0 24px',height:68,display:'flex',alignItems:'center',gap:32}}>
    <a href="#" style={{display:'flex',alignItems:'center'}}><img src="../../assets/logo-lockup.png" alt="CrossBid" style={{height:30,display:'block'}}/></a>
    <nav style={{display:'flex',gap:28,flex:1,justifyContent:'center'}}>{['Product','How it works','Certificates','Pricing','Customers'].map(l=><a key={l} href="#" style={{font:'500 14px/1 var(--font-sans)',color:'var(--text-secondary)',textDecoration:'none'}}>{l}</a>)}</nav>
    <div style={{display:'flex',gap:8}}><Button variant="secondary" size="sm">Sign in</Button><Button variant="inverse" size="sm">Book a demo</Button></div></div></header>}
Object.assign(window,{Nav});