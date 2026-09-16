// Loads CrossBid DS components (bundle if present, else compiles component .jsx sources), then the kit's own babel files in order.
window.CBLoad = async function(root, kitFiles, mount){
  const NS='CrossBidDesignSystem_b81312';
  const comps=['core/Button','core/IconButton','core/Badge','core/Tag','core/Card','core/Tabs','core/Tooltip','forms/Input','forms/Select','forms/Checkbox','forms/Radio','forms/Switch','feedback/Dialog','feedback/Toast','app/NavItem','app/MetricCard','app/VerdictChip','app/RunCard'];
  if(!window[NS]||!window[NS].Button){
    const ns={};window[NS]=ns;
    for(const c of comps){const name=c.split('/')[1];const t=await (await fetch(root+'/components/'+c+'.jsx')).text();
      const deps=[...t.matchAll(/import \{([^}]+)\} from/g)].flatMap(m=>m[1].split(',').map(s=>s.trim()));
      const src=t.replace(/^import .*$/gm,'').replace(/^export /gm,'')+'\n__r('+name+');';
      const code=Babel.transform(src,{presets:['react'],filename:c+'.jsx'}).code;
      new Function('React','__r',...deps,code)(React,v=>ns[name]=v,...deps.map(d=>ns[d]));}
  }
  for(const f of kitFiles){const t=await (await fetch(f)).text();const code=Babel.transform(t,{presets:['react'],filename:f}).code;(0,eval)(code);}
  if(mount) mount();
};
