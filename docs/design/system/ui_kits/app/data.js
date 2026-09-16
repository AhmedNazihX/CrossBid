window.CB_DATA={
 tenders:[
  {id:'2024/S 118-345621',title:'Modernisation of municipal wastewater treatment — Lot 2 (electrical)',buyer:'Comune di Bergamo',country:'IT',due:'In 6 days',phase:'Review',verdict:'conditional',reqs:47,unsupported:3,value:'€2.4M'},
  {id:'2024/S 121-352208',title:'Framework agreement for IT security consulting services',buyer:'Bundesamt für Sicherheit in der Informationstechnik',country:'DE',due:'In 9 days',phase:'Analysis',verdict:'insufficient',reqs:31,unsupported:0,value:'€850k'},
  {id:'2024/S 115-339104',title:'Supply and maintenance of medical imaging equipment',buyer:'Région Auvergne-Rhône-Alpes',country:'FR',due:'In 12 days',phase:'Review',verdict:'go',reqs:58,unsupported:0,value:'€5.1M'},
  {id:'2024/S 119-347810',title:'Road resurfacing programme 2025–2027, north district',buyer:'Gemeente Utrecht',country:'NL',due:'In 14 days',phase:'Confirmed',verdict:'nogo',reqs:22,unsupported:5,value:'€1.2M'},
  {id:'2024/S 123-358443',title:'Cloud hosting for citizen services portal',buyer:'Skatteverket',country:'SE',due:'In 19 days',phase:'Analysis',verdict:'insufficient',reqs:0,unsupported:0,value:'€3.0M'},
  {id:'2024/S 117-343002',title:'School catering services, 14 sites',buyer:'Ayuntamiento de Zaragoza',country:'ES',due:'In 21 days',phase:'Review',verdict:'go',reqs:29,unsupported:0,value:'€670k'},
 ],
 runs:[
  {title:'Tender analysis · 2024/S 118-345621',summary:'Retrieved 47 requirements across 3 lots from 112 pages (IT). Translated to DE. Mapped 6 certificate requests; 3 requirements lack supporting evidence in the company profile (REQ-012, REQ-031, REQ-044).',status:'warning',meta:['Manual','9 steps','4 minutes','Jun 21 at 9:02 AM']},
  {title:'Certificate mapping · 2024/S 115-339104',summary:'Mapped 4 French certificate requests to German equivalents: Qualibat 1552 → HWK Meisterbrief (Elektrotechnik); Attestation URSSAF → Unbedenklichkeitsbescheinigung. All 4 supported.',status:'success',meta:['Scheduled','5 steps','1 minute','Jun 21 at 9:00 AM']},
  {title:'Tender analysis · 2024/S 123-358443',summary:'No verdict — the selection criteria (p. 14–17) are scanned images and not machine-readable. Upload a text version to continue.',status:'danger',statusLabel:'Failed',meta:['Manual','3 steps','40 seconds','Jun 20 at 4:15 PM']},
  {title:'Tender analysis · 2024/S 117-343002',summary:'Retrieved 29 requirements from 48 pages (ES). All requirements supported by profile evidence. Recommended verdict: Go. Awaiting confirmation by Lena Hartmann.',status:'success',meta:['Manual','8 steps','3 minutes','Jun 20 at 11:30 AM']},
 ],
 requirements:[
  {id:'REQ-001',cat:'Selection',src:'p. 14 §3.1.a',orig:'Iscrizione alla Camera di Commercio per attività attinenti all\'oggetto dell\'appalto.',trans:'Registration with the chamber of commerce for activities relevant to the contract.',ev:'Handelsregisterauszug HRB 224871',state:'supported'},
  {id:'REQ-002',cat:'Selection',src:'p. 14 §3.1.b',orig:'Fatturato globale minimo annuo di € 3.000.000 negli ultimi tre esercizi.',trans:'Minimum annual global turnover of €3,000,000 in each of the last three financial years.',ev:'Jahresabschluss 2021–2023 (€3.6M / €4.1M / €4.4M)',state:'supported'},
  {id:'REQ-012',cat:'Selection',src:'p. 15 §3.2.c',orig:'Certificazione SOA categoria OS30 classifica III.',trans:'SOA qualification, category OS30 (electrical systems), class III. No direct DE equivalent — closest: HWK Eintragung Elektrotechnik + reference projects ≥ €1.03M.',ev:'HWK Eintragung found; reference projects missing',state:'partial'},
  {id:'REQ-018',cat:'Technical',src:'p. 17 §4.1',orig:'Certificazione UNI EN ISO 9001:2015 in corso di validità.',trans:'Valid ISO 9001:2015 certification.',ev:'ISO 9001:2015 · TÜV Rheinland · valid to 03/2027',state:'supported'},
  {id:'REQ-031',cat:'Technical',src:'p. 22 §4.4',orig:'Almeno due contratti analoghi eseguiti nel triennio, ciascuno di importo ≥ € 800.000.',trans:'At least two comparable contracts completed in the last three years, each worth ≥ €800,000.',ev:'One reference found (Stadtwerke Bonn, €1.1M). Second not found.',state:'unsupported'},
  {id:'REQ-044',cat:'Award',src:'p. 31 §6.2',orig:'Piano di manutenzione con tempi di intervento garantiti ≤ 4 ore.',trans:'Maintenance plan with guaranteed response time ≤ 4 hours.',ev:'No service-level document in profile',state:'unsupported'},
  {id:'REQ-047',cat:'Formal',src:'p. 38 §8.1',orig:'Garanzia provvisoria pari al 2% dell\'importo a base di gara.',trans:'Bid bond equal to 2% of the estimated contract value (€48,000).',ev:'Bank guarantee facility · Commerzbank · up to €250k',state:'supported'},
 ],
};