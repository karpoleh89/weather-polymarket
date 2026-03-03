import { useState, useEffect, useMemo, useCallback } from "react";
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, ReferenceLine, Area, Bar, Cell
} from "recharts";

// ── Config ─────────────────────────────────────────────────────────────────
const LAT = 51.503164654;
const LON = 0.053166454;
const ICAO = "EGLC";

const GROUPS = {
  ecmwf: { models: ["ecmwf_ifs025_ensemble","ecmwf_aifs025_ensemble"], color:"#38bdf8", label:"ECMWF", w:0.4 },
  gefs:  { models: ["ncep_gefs_seamless"],                              color:"#fb923c", label:"GFS",   w:0.1 },
  icon:  { models: ["icon_seamless_eps","icon_d2_eps"],                 color:"#4ade80", label:"ICON",  w:0.2 },
  ukmo:  { models: ["ukmo_global_ensemble_20km","ukmo_uk_ensemble_2km"],color:"#c084fc", label:"UKMO",  w:0.3 },
};
const ALL_MODELS = Object.values(GROUPS).flatMap(g => g.models);
const fToC = f => +((f - 32) / 1.8).toFixed(1);
const pct = (arr, p) => { const s = [...arr].sort((a,b)=>a-b); return s[Math.max(0,Math.floor(p/100*(s.length-1)))]; };
const windLabel = d => { if(d==null)return"—"; const dirs=["С","СВ","В","ЮВ","Ю","ЮЗ","З","СЗ"]; return dirs[Math.round(d/45)%8]+` ${Math.round(d)}°`; };
const isEastern = d => d!=null && d>=45 && d<=135;

// ── Custom Tooltip ──────────────────────────────────────────────────────────
const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{background:"#0a0f1a",border:"1px solid #1e3a5f",borderRadius:4,padding:"8px 12px",fontSize:11,fontFamily:"'JetBrains Mono',monospace"}}>
      <div style={{color:"#64748b",marginBottom:4}}>{label} GMT</div>
      {payload.map((p,i) => p.value!=null && (
        <div key={i} style={{color:p.color,display:"flex",justifyContent:"space-between",gap:16}}>
          <span>{p.name}</span><span style={{color:"#e2e8f0"}}>{p.value}°C</span>
        </div>
      ))}
    </div>
  );
};

export default function Dashboard() {
  const [ens, setEns] = useState(null);
  const [metarList, setMetarList] = useState([]);
  const [currentConds, setCurrentConds] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fetchErrors, setFetchErrors] = useState({});
  const [activeGroups, setActiveGroups] = useState(new Set(Object.keys(GROUPS)));
  const [day, setDay] = useState(0);
  const [refreshedAt, setRefreshedAt] = useState(null);
  const [tick, setTick] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    const errs = {};

    try {
      const p = new URLSearchParams({
        latitude:LAT, longitude:LON, hourly:"temperature_2m",
        models:ALL_MODELS.join(","), timezone:"GMT",
        past_days:1, forecast_days:3, temperature_unit:"fahrenheit"
      });
      const r = await fetch(`https://ensemble-api.open-meteo.com/v1/ensemble?${p}`);
      setEns(await r.json());
    } catch(e) { errs.ensemble = e.message; }

    try {
      const r = await fetch(`https://aviationweather.gov/api/data/metar?ids=${ICAO}&format=json&hours=12`);
      const d = await r.json();
      setMetarList(Array.isArray(d) ? d : []);
    } catch(e) { errs.metar = e.message; }

    try {
      const p = new URLSearchParams({
        latitude:LAT, longitude:LON,
        current:"temperature_2m,dewpoint_2m,wind_direction_10m,wind_speed_10m,cloud_cover",
        timezone:"GMT"
      });
      const r = await fetch(`https://api.open-meteo.com/v1/forecast?${p}`);
      const d = await r.json();
      setCurrentConds(d.current);
    } catch(e) { errs.current = e.message; }

    setFetchErrors(errs);
    setLoading(false);
    setRefreshedAt(new Date());
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 30*60*1000); return ()=>clearInterval(t); }, [load]);
  useEffect(() => { const t = setInterval(()=>setTick(x=>x+1), 1000); return ()=>clearInterval(t); }, []);

  // ── Parse ensemble ────────────────────────────────────────────────────────
  const series = useMemo(() => {
    if (!ens?.hourly) return [];
    const h = ens.hourly;
    const cols = Object.keys(h).filter(k=>k!=="time");
    const colGroup = {};
    cols.forEach(c => { for(const [g,info] of Object.entries(GROUPS)) if(info.models.some(m=>c.includes(m))){colGroup[c]=g;break;} });

    return h.time.map((t,i) => {
      const dt = new Date(t+"Z");
      const allF = cols.map(c=>h[c][i]).filter(v=>v!=null);
      if(!allF.length) return null;
      const allC = allF.map(fToC);
      const gm = {};
      for(const g of Object.keys(GROUPS)){
        const v = cols.filter(c=>colGroup[c]===g).map(c=>h[c][i]).filter(v=>v!=null).map(fToC);
        if(v.length) gm[g] = +(v.reduce((a,b)=>a+b)/v.length).toFixed(1);
      }
      return {
        time:dt, ts:dt.toISOString().slice(11,16), date:dt.toISOString().slice(0,10),
        p10:pct(allC,10), p25:pct(allC,25), p50:pct(allC,50), p75:pct(allC,75), p90:pct(allC,90),
        mean:+(allC.reduce((a,b)=>a+b)/allC.length).toFixed(1), ...gm,
      };
    }).filter(Boolean);
  }, [ens]);

  const todayStr = useMemo(()=>new Date().toISOString().slice(0,10),[tick]);
  const selDate = useMemo(()=>{ const d=new Date(todayStr+"T00:00:00Z"); d.setUTCDate(d.getUTCDate()+day); return d.toISOString().slice(0,10); },[day,todayStr]);
  const daySeries = useMemo(()=>series.filter(p=>p.date===selDate),[series,selDate]);

  // ── Tmax probabilities ─────────────────────────────────────────────────────
  const probs = useMemo(() => {
    if (!ens?.hourly) return [];
    const h = ens.hourly; const cols = Object.keys(h).filter(k=>k!=="time");
    const colW={}, modCount={}, colMod={};
    cols.forEach(c => { for(const [g,info] of Object.entries(GROUPS)){const m=info.models.find(mo=>c.includes(mo));if(m){colMod[c]={g,m};modCount[m]=(modCount[m]||0)+1;break;}} });
    cols.forEach(c => { const cm=colMod[c];if(!cm)return; const info=GROUPS[cm.g]; colW[c]=info.w/(info.models.length*(modCount[cm.m]||1)); });
    const tw=Object.values(colW).reduce((a,b)=>a+b,0); Object.keys(colW).forEach(k=>colW[k]/=tw);
    const dayIdx=h.time.reduce((acc,t,i)=>{ const dt=new Date(t+"Z"); if(dt.toISOString().slice(0,10)===selDate&&dt.getUTCHours()>=6&&dt.getUTCHours()<=21)acc.push(i); return acc; },[]);
    if(!dayIdx.length) return [];
    const tmaxC={};
    cols.forEach(c=>{ const vals=dayIdx.map(i=>h[c][i]).filter(v=>v!=null); if(vals.length)tmaxC[c]=Math.round(fToC(Math.max(...vals))); });
    const pb={};
    Object.entries(tmaxC).forEach(([c,cv])=>{ pb[cv]=(pb[cv]||0)+(colW[c]||0); });
    const tot=Object.values(pb).reduce((a,b)=>a+b,0);
    return Object.entries(pb).map(([t,p])=>({temp:+t,prob:+(p/tot*100).toFixed(1),narrow:+t%5===0})).filter(d=>d.prob>=0.5).sort((a,b)=>a.temp-b.temp);
  }, [ens, selDate]);

  // ── Parse METAR ────────────────────────────────────────────────────────────
  const metarP = useMemo(() => metarList
    .filter(m=>m.temp!=null)
    .map(m=>({
      time:new Date((m.obsTime||m.reportTime||"").replace(" ","T")+"Z"),
      temp:+m.temp, dew:m.dewpoint!=null?+m.dewpoint:null,
      def:m.dewpoint!=null?+(m.temp-m.dewpoint).toFixed(1):null,
      wdir:m.wdir!=null?+m.wdir:null, wspd:m.wspd!=null?+m.wspd:null,
      raw:m.rawOb||m.rawob||"",
    }))
    .map(m=>({...m,ts:m.time.toISOString().slice(11,16)}))
    .sort((a,b)=>a.time-b.time)
  ,[metarList]);

  // ── Combined chart data ────────────────────────────────────────────────────
  const chartData = useMemo(() => {
    const eMap=Object.fromEntries(daySeries.map(p=>[p.ts,p]));
    const mToday=metarP.filter(m=>m.time.toISOString().slice(0,10)===selDate);
    const mMap=Object.fromEntries(mToday.map(m=>[m.ts,m]));
    const allTs=new Set([...daySeries.map(p=>p.ts),...mToday.map(m=>m.ts)]);
    return [...allTs].sort().map(ts=>({ts,...eMap[ts],metar:mMap[ts]?.temp,def:mMap[ts]?.def}));
  },[daySeries,metarP,selDate]);

  // ── Nowcast signals ────────────────────────────────────────────────────────
  const signals = useMemo(() => {
    if(metarP.length<2) return null;
    const lat=metarP[metarP.length-1], prev=metarP[metarP.length-2];
    const dth=(lat.time-prev.time)/3600000;
    const dtdt=dth>0?+((lat.temp-prev.temp)/dth).toFixed(2):0;
    const close=daySeries.reduce((b,p)=>!b||Math.abs(p.time-lat.time)<Math.abs(b.time-lat.time)?p:b,null);
    const delta=close?+(lat.temp-close.mean).toFixed(1):null;
    const wdir=lat.wdir??currentConds?.wind_direction_10m;
    const defTrend=metarP.length>=3&&metarP.at(-1).def!=null&&metarP.at(-3).def!=null
      ?+(metarP.at(-1).def-metarP.at(-3).def).toFixed(1):0;
    return {lat,dtdt,delta,wdir,isE:isEastern(wdir),def:lat.def,defTrend,modelTemp:close?.mean};
  },[metarP,daySeries,currentConds]);

  const hints = useMemo(()=>{
    if(!signals) return [];
    const h=[];
    if(signals.delta>=0.8) h.push({type:"bull",icon:"↑",title:"Прогрев опережает модель",body:`Факт +${signals.delta}°C выше модели. Tmax вероятно превысит прогноз на 0.5–1°C`});
    else if(signals.delta<=-0.8) h.push({type:"bear",icon:"↓",title:"Прогрев отстаёт от модели",body:`Факт ${signals.delta}°C ниже модели. Tmax может не достичь прогноза`});
    if(signals.dtdt>1.5) h.push({type:"bull",icon:"🔥",title:`dT/dt = +${signals.dtdt}°C/ч`,body:"Быстрый прогрев — пик температуры придёт раньше прогноза"});
    else if(signals.dtdt<-0.5) h.push({type:"bear",icon:"❄",title:`dT/dt = ${signals.dtdt}°C/ч`,body:"Охлаждение — пик дня вероятно уже позади"});
    if(signals.def>8&&signals.defTrend>1) h.push({type:"bull",icon:"💧",title:`Дефицит т/р ${signals.def}°C ↑`,body:`Воздух сохнет (+${signals.defTrend}°C). Риск пробоя Tmax вверх`});
    if(signals.isE) h.push({type:"warn",icon:"💨",title:`Восточный ветер ${signals.wdir}°`,body:"Бриз Темзы — холодный воздух с эстуария может обрубить прогрев EGLC за 15 мин"});
    return h;
  },[signals]);

  const cc = currentConds;
  const nowStr = new Date().toUTCString().slice(17,22);
  const dayLabels = ["Сегодня","Завтра","Послезавтра"];

  const styles = {
    bull: {border:"1px solid #166534",background:"#052e16",borderLeft:"3px solid #4ade80"},
    bear: {border:"1px solid #7f1d1d",background:"#1c0606",borderLeft:"3px solid #f87171"},
    warn: {border:"1px solid #854d0e",background:"#1c1003",borderLeft:"3px solid #fbbf24"},
  };

  return (
    <div style={{minHeight:"100vh",background:"#060b14",color:"#cbd5e1",fontFamily:"'JetBrains Mono',monospace",fontSize:12,padding:12}}>

      {/* ── TOP BAR ── */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:12,paddingBottom:10,borderBottom:"1px solid #0f2035"}}>
        <div>
          <div style={{fontSize:16,fontWeight:700,color:"#e2e8f0",letterSpacing:1}}>
            ✈ EGLC · LONDON CITY AIRPORT
          </div>
          <div style={{color:"#334155",fontSize:11,marginTop:2}}>WEATHER ENSEMBLE DASHBOARD · POLYMARKET TMAX ANALYSIS</div>
        </div>
        <div style={{textAlign:"right"}}>
          <button onClick={load} disabled={loading}
            style={{background:"#0f2035",border:"1px solid #1e3a5f",color:"#38bdf8",padding:"4px 12px",borderRadius:3,cursor:"pointer",fontSize:11,marginBottom:4}}>
            {loading?"LOADING...":"↻ REFRESH"}
          </button>
          <div style={{color:"#1e3a5f",fontSize:10}}>
            {refreshedAt?`UPDATED ${refreshedAt.toUTCString().slice(17,22)} UTC`:"—"}
          </div>
          <div style={{color:"#334155",fontSize:10,marginTop:1}}>NOW {nowStr} UTC</div>
        </div>
      </div>

      {/* ── CURRENT CONDITIONS ── */}
      {cc && (
        <div style={{display:"grid",gridTemplateColumns:"repeat(6,1fr)",gap:8,marginBottom:12}}>
          {[
            ["TEMP","temperature_2m",v=>`${v.toFixed(1)}°C`,null],
            ["DEW PT","dewpoint_2m",v=>`${v.toFixed(1)}°C`,null],
            ["T–Td",null,()=>`${(cc.temperature_2m-cc.dewpoint_2m).toFixed(1)}°C`,v=>(cc.temperature_2m-cc.dewpoint_2m)>8?"#fbbf24":null],
            ["WIND DIR","wind_direction_10m",v=>windLabel(v),v=>isEastern(v)?"#f87171":null],
            ["WIND SPD","wind_speed_10m",v=>`${v} km/h`,null],
            ["CLOUD","cloud_cover",v=>`${v}%`,null],
          ].map(([label,key,fmt,colorFn],i)=>{
            const val = key?cc[key]:null;
            const color = colorFn?(key?colorFn(cc[key]):colorFn()):"#e2e8f0";
            return (
              <div key={i} style={{background:"#0a1628",border:"1px solid #0f2035",borderRadius:4,padding:"8px 10px"}}>
                <div style={{color:"#334155",fontSize:9,letterSpacing:1,marginBottom:3}}>{label}</div>
                <div style={{fontSize:15,fontWeight:700,color:color||"#e2e8f0"}}>{fmt(val)}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── NOWCAST HINTS ── */}
      {hints.length>0 && (
        <div style={{display:"grid",gridTemplateColumns:`repeat(${Math.min(hints.length,2)},1fr)`,gap:6,marginBottom:12}}>
          {hints.map((h,i)=>(
            <div key={i} style={{...styles[h.type],borderRadius:3,padding:"7px 10px",display:"flex",gap:8,alignItems:"flex-start"}}>
              <span style={{fontSize:14}}>{h.icon}</span>
              <div>
                <div style={{fontWeight:700,color:"#e2e8f0",fontSize:11,marginBottom:1}}>{h.title}</div>
                <div style={{color:"#94a3b8",fontSize:10}}>{h.body}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── DAY SELECTOR + MODEL TOGGLES ── */}
      <div style={{display:"flex",gap:8,marginBottom:10,alignItems:"center",flexWrap:"wrap"}}>
        {dayLabels.map((l,i)=>(
          <button key={i} onClick={()=>setDay(i)}
            style={{background:day===i?"#0f2a4a":"#0a1628",border:`1px solid ${day===i?"#38bdf8":"#0f2035"}`,color:day===i?"#38bdf8":"#475569",padding:"4px 14px",borderRadius:3,cursor:"pointer",fontSize:11,letterSpacing:0.5}}>
            {l}
          </button>
        ))}
        <div style={{width:1,height:20,background:"#0f2035",margin:"0 4px"}}/>
        <span style={{color:"#334155",fontSize:10}}>МОДЕЛИ:</span>
        {Object.entries(GROUPS).map(([k,g])=>(
          <button key={k} onClick={()=>{const n=new Set(activeGroups);n.has(k)?n.delete(k):n.add(k);setActiveGroups(n);}}
            style={{background:activeGroups.has(k)?"#0a1628":"#060b14",border:`1px solid ${activeGroups.has(k)?g.color:"#0f2035"}`,color:activeGroups.has(k)?g.color:"#334155",padding:"3px 10px",borderRadius:12,cursor:"pointer",fontSize:10}}>
            {g.label} ×{g.w}
          </button>
        ))}
      </div>

      {/* ── MAIN CHART ── */}
      <div style={{background:"#0a1628",border:"1px solid #0f2035",borderRadius:6,padding:"12px 8px",marginBottom:10}}>
        <div style={{color:"#334155",fontSize:10,letterSpacing:1,marginBottom:8,paddingLeft:8}}>
          TEMPERATURE ENSEMBLE · {selDate} · °C · {daySeries.length} DATA POINTS
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={chartData} margin={{top:5,right:16,bottom:0,left:-8}}>
            <CartesianGrid strokeDasharray="2 4" stroke="#0d1f35"/>
            <XAxis dataKey="ts" stroke="#1e3a5f" tick={{fontSize:9,fill:"#475569"}} interval={3}/>
            <YAxis stroke="#1e3a5f" tick={{fontSize:9,fill:"#475569"}} tickFormatter={v=>`${v}°`} domain={["auto","auto"]}/>
            <Tooltip content={<ChartTooltip/>}/>
            <Legend wrapperStyle={{fontSize:10,color:"#64748b",paddingTop:4}}/>
            {/* Percentile envelope */}
            <Line dataKey="p90" stroke="#1e3a5f" strokeWidth={1} dot={false} name="p90" strokeDasharray="2 4" legendType="none"/>
            <Line dataKey="p10" stroke="#1e3a5f" strokeWidth={1} dot={false} name="p10" strokeDasharray="2 4" legendType="none"/>
            <Line dataKey="p50" stroke="#334155" strokeWidth={1.5} dot={false} name="Медиана p50" strokeDasharray="5 3"/>
            {/* Model group means */}
            {Object.entries(GROUPS).map(([k,g])=>activeGroups.has(k)&&(
              <Line key={k} dataKey={k} stroke={g.color} strokeWidth={1.5} dot={false} name={g.label} connectNulls/>
            ))}
            {/* Weighted mean */}
            <Line dataKey="mean" stroke="#e2e8f0" strokeWidth={2.5} strokeDasharray="6 3" dot={false} name="Среднее (взв.)" connectNulls/>
            {/* METAR actual */}
            <Line dataKey="metar" stroke="#f87171" strokeWidth={2} name="METAR факт"
              dot={{r:4,fill:"#f87171",stroke:"#7f1d1d",strokeWidth:1}} connectNulls/>
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* ── BOTTOM ROW ── */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10,marginBottom:10}}>

        {/* Probability chart */}
        <div style={{background:"#0a1628",border:"1px solid #0f2035",borderRadius:6,padding:"12px 8px"}}>
          <div style={{color:"#334155",fontSize:10,letterSpacing:1,marginBottom:8,paddingLeft:8}}>
            ВЕРОЯТНОСТЬ TMAX · POLYMARKET · {selDate}
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={probs} layout="vertical" margin={{top:0,right:36,bottom:0,left:8}}>
              <CartesianGrid strokeDasharray="2 4" stroke="#0d1f35" horizontal={false}/>
              <XAxis type="number" domain={[0,100]} stroke="#1e3a5f" tick={{fontSize:9,fill:"#475569"}} tickFormatter={v=>`${v}%`}/>
              <YAxis type="category" dataKey="temp" stroke="#1e3a5f" tick={{fontSize:10,fill:"#94a3b8"}} width={28} tickFormatter={v=>`${v}°`}/>
              <Tooltip contentStyle={{background:"#0a0f1a",border:"1px solid #1e3a5f",borderRadius:4,fontSize:11,fontFamily:"monospace"}}
                formatter={(v)=>[`${v}%`,"P(Tmax)"]}/>
              <Bar dataKey="prob" radius={[0,3,3,0]} label={{position:"right",fontSize:10,fill:"#64748b",formatter:v=>`${v}%`}}>
                {probs.map((e,i)=><Cell key={i} fill={e.narrow?"#f59e0b":"#38bdf8"} fillOpacity={0.85}/>)}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
          <div style={{display:"flex",gap:16,paddingLeft:8,marginTop:4}}>
            <span style={{color:"#64748b",fontSize:9}}><span style={{color:"#f59e0b"}}>■</span> УЗКО (кратно 5)</span>
            <span style={{color:"#64748b",fontSize:9}}><span style={{color:"#38bdf8"}}>■</span> ШИРОКО</span>
          </div>
        </div>

        {/* Dew point deficit */}
        <div style={{background:"#0a1628",border:"1px solid #0f2035",borderRadius:6,padding:"12px 8px"}}>
          <div style={{color:"#334155",fontSize:10,letterSpacing:1,marginBottom:8,paddingLeft:8}}>
            ДЕФИЦИТ ТОЧКИ РОСЫ (T–Td) · METAR EGLC
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={chartData.filter(d=>d.def!=null)} margin={{top:5,right:16,bottom:0,left:-12}}>
              <CartesianGrid strokeDasharray="2 4" stroke="#0d1f35"/>
              <XAxis dataKey="ts" stroke="#1e3a5f" tick={{fontSize:9,fill:"#475569"}} interval={2}/>
              <YAxis stroke="#1e3a5f" tick={{fontSize:9,fill:"#475569"}} tickFormatter={v=>`${v}°`}/>
              <Tooltip contentStyle={{background:"#0a0f1a",border:"1px solid #1e3a5f",borderRadius:4,fontSize:11,fontFamily:"monospace"}}
                formatter={(v)=>[`${v}°C`,"T–Td"]}/>
              <ReferenceLine y={8} stroke="#fbbf24" strokeDasharray="3 3" label={{value:"Сухо >8°",fontSize:9,fill:"#fbbf24",position:"right"}}/>
              <Area dataKey="def" stroke="#4ade80" fill="#052e16" strokeWidth={2} name="T–Td"
                dot={{r:4,fill:"#4ade80",stroke:"#166534",strokeWidth:1}}/>
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── METAR TABLE ── */}
      {metarP.length>0 && (
        <div style={{background:"#0a1628",border:"1px solid #0f2035",borderRadius:6,padding:"10px 12px"}}>
          <div style={{color:"#334155",fontSize:10,letterSpacing:1,marginBottom:8}}>METAR EGLC · ПОСЛЕДНИЕ НАБЛЮДЕНИЯ</div>
          <table style={{width:"100%",borderCollapse:"collapse"}}>
            <thead>
              <tr style={{color:"#1e3a5f",borderBottom:"1px solid #0f2035"}}>
                {["UTC","T°C","Td°C","T–Td","ВЕТЕР","RAW METAR"].map(h=>(
                  <th key={h} style={{textAlign:h==="RAW METAR"?"left":"right",padding:"3px 8px",fontWeight:400,fontSize:9,letterSpacing:1}}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...metarP].reverse().slice(0,8).map((m,i)=>(
                <tr key={i} style={{borderBottom:"1px solid #060b14"}}>
                  <td style={{padding:"5px 8px",color:"#475569",textAlign:"right"}}>{m.ts}</td>
                  <td style={{padding:"5px 8px",color:"#e2e8f0",fontWeight:700,textAlign:"right"}}>{m.temp.toFixed(1)}</td>
                  <td style={{padding:"5px 8px",color:"#60a5fa",textAlign:"right"}}>{m.dew?.toFixed(1)??"—"}</td>
                  <td style={{padding:"5px 8px",color:m.def>8?"#fbbf24":"#64748b",fontWeight:m.def>8?700:400,textAlign:"right"}}>{m.def?.toFixed(1)??"—"}</td>
                  <td style={{padding:"5px 8px",color:m.wdir>=45&&m.wdir<=135?"#f87171":"#64748b",fontWeight:m.wdir>=45&&m.wdir<=135?700:400,textAlign:"right"}}>
                    {m.wdir!=null?`${m.wdir}° / ${m.wspd}кт`:"—"}
                  </td>
                  <td style={{padding:"5px 8px",color:"#1e3a5f",fontFamily:"monospace",fontSize:10,maxWidth:320,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{m.raw}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── ERRORS ── */}
      {Object.keys(fetchErrors).length>0 && (
        <div style={{marginTop:8,background:"#1c0606",border:"1px solid #7f1d1d",borderRadius:4,padding:"6px 10px",fontSize:10,color:"#fca5a5"}}>
          {Object.entries(fetchErrors).map(([k,v])=><div key={k}>⚠ {k.toUpperCase()}: {v}</div>)}
        </div>
      )}

      {/* ── FOOTER ── */}
      <div style={{marginTop:12,color:"#1e3a5f",fontSize:9,textAlign:"center",letterSpacing:1}}>
        ENSEMBLE: ECMWF IFS+AIFS · GFS · ICON-EPS+D2 · UKMO GLOBAL+UK · METAR: {ICAO} · DATA: OPEN-METEO + AVIATIONWEATHER.GOV
      </div>
    </div>
  );
}
