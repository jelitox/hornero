"""Offline interactive graph explorer embedded in the knowledge report."""

from __future__ import annotations

import html
import json
from typing import Any


CSS = """
#graph-explorer{margin:1.5rem 0;border:1px solid #d4d4d4;border-radius:.6rem;overflow:hidden}
.explorer-tools{display:flex;gap:.5rem;flex-wrap:wrap;padding:.75rem;background:#fffbeb}
.explorer-tools input,.explorer-tools select{padding:.45rem;border:1px solid #a3a3a3;border-radius:.3rem}
.explorer-layout{display:grid;grid-template-columns:minmax(0,3fr) minmax(15rem,1fr);min-height:34rem}
#graph-canvas{width:100%;height:34rem;background:#fafafa;cursor:grab}
#graph-detail{padding:1rem;border-left:1px solid #d4d4d4;overflow:auto;max-height:34rem}
.graph-edge{stroke:#a3a3a3;stroke-opacity:.42}.graph-node{stroke:#fff;stroke-width:1.5;cursor:pointer}
.graph-label{font:10px system-ui;pointer-events:none}.muted{color:#737373}
@media(max-width:760px){.explorer-layout{grid-template-columns:1fr}#graph-detail{border-left:0;border-top:1px solid #d4d4d4}}
"""


def _json(data: Any) -> str:
    # JSON inside a script element must not be able to terminate that element.
    return (
        json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    )


def section(nodes: list[dict[str, Any]], edges: list[dict[str, str]]) -> str:
    groups = sorted({str(node.get("group", "other")) for node in nodes})
    options = "".join(
        f'<option value="{html.escape(group, quote=True)}">{html.escape(group)}</option>'
        for group in groups
    )
    payload = {"nodes": nodes, "edges": edges}
    return f"""
<section id="graph-explorer" data-dashboard="offline-interactive-v1">
  <div class="explorer-tools">
    <input id="graph-search" type="search" placeholder="Fuzzy search nodes" aria-label="Search graph">
    <select id="graph-layer" aria-label="Architectural layer"><option value="">All layers</option>{options}</select>
    <select id="graph-persona" aria-label="Detail persona"><option value="engineer">Engineer</option><option value="executive">Executive</option><option value="onboarding">Onboarding</option></select>
    <button id="graph-tour" type="button">Guided tour</button>
    <span id="graph-count" class="muted"></span>
  </div>
  <div class="explorer-layout">
    <svg id="graph-canvas" viewBox="0 0 900 540" role="img" aria-label="Interactive knowledge graph"></svg>
    <aside id="graph-detail"><h3>Explore the graph</h3><p>Search or select a node to inspect its relationships and source.</p></aside>
  </div>
</section>
<script id="graph-data" type="application/json">{_json(payload)}</script>
<script id="dashboard-app">
(()=>{{
  'use strict';
  const data=JSON.parse(document.getElementById('graph-data').textContent),svg=document.getElementById('graph-canvas');
  const search=document.getElementById('graph-search'),layer=document.getElementById('graph-layer'),persona=document.getElementById('graph-persona');
  const detail=document.getElementById('graph-detail'),count=document.getElementById('graph-count');
  const NS='http://www.w3.org/2000/svg',colors={{requirement:'#b45309',task:'#2563eb',symbol:'#7c3aed',module:'#059669',document:'#0891b2',decision:'#dc2626',artifact:'#65a30d',other:'#737373'}};
  const esc=s=>String(s??'').replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}}[c]));
  const hash=s=>{{let h=2166136261;for(const c of s)h=Math.imul(h^c.charCodeAt(0),16777619);return h>>>0}};
  const fuzzy=(value,q)=>{{let i=0;for(const c of value.toLowerCase())if(c===q[i])i++;return i===q.length}};
  let tour=0;
  function render(){{
    const q=search.value.trim().toLowerCase(),wanted=layer.value;
    const nodes=data.nodes.filter(n=>(!wanted||n.group===wanted)&&(!q||fuzzy(`${{n.id}} ${{n.title}} ${{n.summary}}`,q))).slice(0,350);
    const ids=new Set(nodes.map(n=>n.id)),links=data.edges.filter(e=>ids.has(e.source)&&ids.has(e.target)).slice(0,900);
    const positions=new Map(nodes.map((n,i)=>{{const h=hash(n.id),ring=120+(h%120),angle=(h%6283)/1000;return[n.id,{{x:450+Math.cos(angle)*ring,y:270+Math.sin(angle)*ring}}]}}));
    svg.replaceChildren();
    for(const edge of links){{const a=positions.get(edge.source),b=positions.get(edge.target),line=document.createElementNS(NS,'line');line.setAttribute('x1',a.x);line.setAttribute('y1',a.y);line.setAttribute('x2',b.x);line.setAttribute('y2',b.y);line.setAttribute('class','graph-edge');line.dataset.rel=edge.rel;svg.append(line)}}
    for(const node of nodes){{const p=positions.get(node.id),circle=document.createElementNS(NS,'circle');circle.setAttribute('cx',p.x);circle.setAttribute('cy',p.y);circle.setAttribute('r',node.kind==='requirement'?8:5);circle.setAttribute('fill',colors[node.kind]||colors[node.group]||colors.other);circle.setAttribute('class','graph-node');circle.tabIndex=0;circle.addEventListener('click',()=>show(node,links));svg.append(circle);if(nodes.length<90){{const label=document.createElementNS(NS,'text');label.setAttribute('x',p.x+7);label.setAttribute('y',p.y+3);label.setAttribute('class','graph-label');label.textContent=node.title.slice(0,28);svg.append(label)}}}}
    count.textContent=`${{nodes.length}} nodes · ${{links.length}} relations`;
  }}
  function show(node,links){{
    const related=links.filter(e=>e.source===node.id||e.target===node.id).slice(0,18);
    const compact=persona.value==='executive';
    detail.innerHTML=`<h3>${{esc(node.title)}}</h3><p><span class="muted">${{esc(node.kind)}} · ${{esc(node.group)}}</span></p><p>${{esc(node.summary)}}</p>`+
      (compact?'':`<p><code>${{esc(node.id)}}</code></p><p><b>Source:</b> ${{esc(node.source||'derived')}}</p>`)+
      `<h4>Relations</h4><ul>${{related.map(e=>`<li>${{esc(e.rel)}} → <code>${{esc(e.source===node.id?e.target:e.source)}}</code></li>`).join('')}}</ul>`;
  }}
  search.addEventListener('input',render);layer.addEventListener('change',render);persona.addEventListener('change',render);
  document.getElementById('graph-tour').addEventListener('click',()=>{{const ordered=data.nodes.filter(n=>['requirement','decision','module','symbol'].includes(n.kind)).sort((a,b)=>a.kind.localeCompare(b.kind)||a.title.localeCompare(b.title));if(ordered.length)show(ordered[tour++%ordered.length],data.edges)}});
  render();
}})();
</script>"""
