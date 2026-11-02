import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { LocateFixed, Minus, Plus } from 'lucide-react';
import { Plan, Checkpoint, colors, labels, dateTime } from './types';
const empty: GeoJSON.FeatureCollection = {type:'FeatureCollection',features:[]};
export default function TripMap({plan, selected, hour, heatVisible, onCheckpoint}: {plan:Plan|null; selected:string|null; hour:number; heatVisible:boolean; onCheckpoint:(point:Checkpoint)=>void}) {
 const element = useRef<HTMLDivElement>(null), map = useRef<maplibregl.Map|null>(null);
 const [ready,setReady]=useState(false),[mapError,setMapError]=useState('');
 const current = useRef({plan,selected,onCheckpoint}); current.current={plan,selected,onCheckpoint};
 const fit = () => { const coords=current.current.plan?.routes.flatMap(r=>r.geometry.coordinates); if(coords?.length){const bounds=new maplibregl.LngLatBounds();coords.forEach(p=>bounds.extend([p[0],p[1]])); map.current?.fitBounds(bounds,{padding:65,duration:800,maxZoom:11});}};
 useEffect(()=>{
  if(!element.current) return;
  const m=new maplibregl.Map({container:element.current,center:[-93.2,37.8],zoom:4,attributionControl:{compact:true},style:'https://tiles.openfreemap.org/styles/positron'});
  map.current=m;
  m.on('error',()=>setMapError('Some map tiles could not load. Route results remain available.'));
  m.on('load',()=>{
   ['routes','selected','points','heat','endpoints'].forEach(id=>m.addSource(id,{type:'geojson',data:empty}));
   m.addLayer({id:'heat',type:'heatmap',source:'heat',paint:{'heatmap-weight':['get','weight'],'heatmap-intensity':.9,'heatmap-radius':65,'heatmap-opacity':.55,'heatmap-color':['interpolate',['linear'],['heatmap-density'],0,'rgba(38,167,135,0)',.15,'rgba(38,167,135,.35)',.35,'#dfc94f',.6,'#ed8a45',.8,'#df5863',1,'#9d436c']}});
   m.addLayer({id:'route-casing',type:'line',source:'routes',paint:{'line-color':'#ffffff','line-width':8,'line-opacity':.8},layout:{'line-join':'round','line-cap':'round'}});
   m.addLayer({id:'routes',type:'line',source:'routes',paint:{'line-color':'#788b9c','line-width':4,'line-opacity':.7},layout:{'line-join':'round','line-cap':'round'}});
   m.addLayer({id:'selected-casing',type:'line',source:'selected',paint:{'line-color':'#ffffff','line-width':10},layout:{'line-join':'round','line-cap':'round'}});
   m.addLayer({id:'selected',type:'line',source:'selected',paint:{'line-color':'#157f72','line-width':5},layout:{'line-join':'round','line-cap':'round'}});
   m.addLayer({id:'points',type:'circle',source:'points',paint:{'circle-color':['get','color'],'circle-radius':['interpolate',['linear'],['zoom'],3,3,9,6],'circle-stroke-color':'white','circle-stroke-width':2}});
   m.addLayer({id:'endpoints',type:'circle',source:'endpoints',paint:{'circle-radius':8,'circle-color':'#152a36','circle-stroke-color':'white','circle-stroke-width':3}});
   m.on('click','points',e=>{const id=e.features?.[0]?.properties?.id;const cp=current.current.plan?.routes.find(r=>r.id===current.current.selected)?.checkpoints.find(p=>p.id===id);if(cp){current.current.onCheckpoint(cp); const content=document.createElement('div'); const title=document.createElement('strong');title.textContent=`${labels[cp.risk.level]} risk · mile ${Math.round(cp.distance_miles)}`;const time=document.createElement('p');time.textContent=dateTime(cp.eta);content.append(title,time);new maplibregl.Popup({offset:12}).setLngLat([cp.longitude,cp.latitude]).setDOMContent(content).addTo(m);}});
   m.on('mouseenter','points',()=>m.getCanvas().style.cursor='pointer');m.on('mouseleave','points',()=>m.getCanvas().style.cursor='');setReady(true);
  });
  return ()=>{setReady(false);m.remove();map.current=null;};
 },[]);
 useEffect(()=>{if(!ready||!map.current||!plan)return;const m=map.current;const route=plan.routes.find(r=>r.id===selected);
  (m.getSource('routes') as maplibregl.GeoJSONSource).setData({type:'FeatureCollection',features:plan.routes.filter(r=>r.id!==selected).map(r=>({type:'Feature',properties:{id:r.id},geometry:r.geometry}))});
  (m.getSource('selected') as maplibregl.GeoJSONSource).setData(route?{type:'Feature',properties:{},geometry:route.geometry}:empty);
  (m.getSource('points') as maplibregl.GeoJSONSource).setData({type:'FeatureCollection',features:(route?.checkpoints??[]).map(p=>({type:'Feature',properties:{id:p.id,color:colors[p.risk.level]},geometry:{type:'Point',coordinates:[p.longitude,p.latitude]}}))});
  (m.getSource('endpoints') as maplibregl.GeoJSONSource).setData({type:'FeatureCollection',features:[plan.request.origin,plan.request.destination].map(p=>({type:'Feature',properties:{},geometry:{type:'Point',coordinates:[p.longitude,p.latitude]}}))});
 },[ready,plan,selected]);
 useEffect(()=>{if(ready&&plan)fit();},[ready,plan]);
 useEffect(()=>{if(!ready||!map.current)return; const m=map.current;m.setLayoutProperty('heat','visibility',heatVisible?'visible':'none');
  (m.getSource('heat') as maplibregl.GeoJSONSource).setData({type:'FeatureCollection',features:(plan?.heatmap.points??[]).flatMap(p=>{const v=p.values[hour];return v&&v.score!==null?[{type:'Feature' as const,properties:{weight: .08+v.score*.23},geometry:{type:'Point' as const,coordinates:[p.longitude,p.latitude]}}]:[];})});
 },[ready,plan,hour,heatVisible]);
 return <><div className="map-canvas" ref={element} aria-label="Trip routes and forecast corridor map"/><div className="map-controls"><button title="Zoom in" onClick={()=>map.current?.zoomIn()}><Plus size={17}/></button><button title="Zoom out" onClick={()=>map.current?.zoomOut()}><Minus size={17}/></button><button title="Fit trip" onClick={fit}><LocateFixed size={17}/></button></div>{mapError&&<div className="map-tile-warning">{mapError}</div>}</>;
}
