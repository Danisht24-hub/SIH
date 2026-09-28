import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import Plot from 'react-plotly.js'
import './index.css'

type Stats = { observations:number; routes:number; airlines:number; valid:number; imputed:number; outliers:number; first_scrape:string|null; last_scrape:string|null }
type Route = { origin:string; destination:string; route_weight:string|number; source:string; active:boolean }
type IndexRow = { index_date:string; frequency:string; lead_window_days:number; index_value:number; route_count:number; methodology:string }
type TrendRow = { day:string; observations:number; min_fare:number; median_fare:number; avg_fare:number }
const API = (window as any).__COMPARIFY_API_URL__ || import.meta.env.VITE_API_URL || 'http://localhost:8000'

function App(){
 const [stats,setStats]=useState<Stats|null>(null); const [routes,setRoutes]=useState<Route[]>([]); const [indices,setIndices]=useState<IndexRow[]>([]); const [trend,setTrend]=useState<TrendRow[]>([]); const [lead,setLead]=useState(1); const [route,setRoute]=useState('DEL-BOM'); const [loading,setLoading]=useState(true)
 const [origin,destination]=route.split('-')
 const load=async()=>{setLoading(true); try{
   const [s,r,i,t]=await Promise.all([fetch(`${API}/stats`).then(x=>x.json()),fetch(`${API}/routes`).then(x=>x.json()),fetch(`${API}/index?lead_days=${lead}`).then(x=>x.json()),fetch(`${API}/trend?origin=${origin}&destination=${destination}&days=30&lead_days=${lead}`).then(x=>x.json())]);
   setStats(s);setRoutes(r.routes||[]);setIndices(i.index||[]);setTrend(t.trend||[])
 } finally {setLoading(false)}}
 useEffect(()=>{load()},[lead,route])
 const daily=useMemo(()=>indices.filter(x=>x.frequency==='daily').slice(0,30).reverse(),[indices])
 return <div className="min-h-screen p-6 md:p-10">
  <header className="max-w-7xl mx-auto mb-8"><div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4"><div><p className="text-sm font-semibold text-indigo-600">AETHER · COMPARIFY</p><h1 className="text-3xl md:text-4xl font-bold mt-1">Real-time Airfare Price Index</h1><p className="text-slate-500 mt-2">Route tracking, fare history and APIx analytics.</p></div><div className="flex gap-2"><select className="border rounded-xl px-3 py-2 bg-white" value={route} onChange={e=>setRoute(e.target.value)}>{routes.map(r=><option key={`${r.origin}-${r.destination}`}>{r.origin}-{r.destination}</option>)}</select><select className="border rounded-xl px-3 py-2 bg-white" value={lead} onChange={e=>setLead(Number(e.target.value))}>{[1,7,15,30,45].map(x=><option key={x} value={x}>T+{x}</option>)}</select></div></div></header>
  <main className="max-w-7xl mx-auto space-y-6">
   <section className="grid grid-cols-2 md:grid-cols-6 gap-4">{[['Observations',stats?.observations],['Routes',stats?.routes],['Airlines',stats?.airlines],['Valid',stats?.valid],['Imputed',stats?.imputed],['Outliers',stats?.outliers]].map(([k,v])=><div className="card p-5" key={String(k)}><p className="text-sm text-slate-500">{k}</p><p className="text-2xl font-bold mt-2">{loading?'—':String(v??0)}</p></div>)}</section>
   <section className="grid lg:grid-cols-3 gap-6"><div className="card p-5 lg:col-span-2"><div className="flex justify-between"><div><h2 className="font-semibold">Fare trend · {route}</h2><p className="text-sm text-slate-500">Median and average fare over recent observations</p></div></div><Plot className="w-full" data={[{x:trend.map(x=>x.day),y:trend.map(x=>x.median_fare),type:'scatter',mode:'lines+markers',name:'Median Fare'},{x:trend.map(x=>x.day),y:trend.map(x=>x.avg_fare),type:'scatter',mode:'lines',name:'Average Fare'}]} layout={{autosize:true,height:360,margin:{l:55,r:20,t:20,b:45},legend:{orientation:'h'},yaxis:{title:'INR'},paper_bgcolor:'transparent',plot_bgcolor:'transparent'}} useResizeHandler config={{responsive:true}} /></div>
   <div className="card p-5"><h2 className="font-semibold">APIx</h2><p className="text-sm text-slate-500">Laspeyres-style weighted price relatives</p><Plot data={[{x:daily.map(x=>x.index_date),y:daily.map(x=>x.index_value),type:'scatter',mode:'lines+markers',name:'APIx'}]} layout={{autosize:true,height:360,margin:{l:50,r:10,t:20,b:45},yaxis:{title:'Index (base 100)'},paper_bgcolor:'transparent',plot_bgcolor:'transparent'}} useResizeHandler config={{responsive:true}} /></div></section>
   <section className="card p-5"><h2 className="font-semibold mb-4">Configured route basket</h2><div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left text-slate-500 border-b"><th className="py-3">Route</th><th>Weight</th><th>Source</th><th>Active</th></tr></thead><tbody>{routes.map(r=><tr className="border-b last:border-0" key={`${r.origin}-${r.destination}`}><td className="py-3 font-medium">{r.origin} → {r.destination}</td><td>{r.route_weight}</td><td>{r.source}</td><td>{r.active?'Yes':'No'}</td></tr>)}</tbody></table></div></section>
   <section className="card p-5"><h2 className="font-semibold mb-2">Methodology</h2><p className="text-sm text-slate-600">APIx uses route weights and current/base route median fares. Raw observations remain in PostgreSQL; cleaning flags, imputation and outlier status are retained for auditability.</p></section>
  </main>
 </div>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>)
