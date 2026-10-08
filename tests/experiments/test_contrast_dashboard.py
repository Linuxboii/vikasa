"""Portable evidence embeds data safely instead of interpreting report text as HTML."""

import importlib
import json
import shutil
import subprocess
from html.parser import HTMLParser

import pytest


class EvidenceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_data = False
        self.data = ""
        self.scripts = []
        self.external = []
        self.in_controller = False
        self.controller = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.scripts.append(attrs)
            self.in_data = attrs.get("id") == "evidence"
            self.in_controller = not self.in_data
        if tag == "script" and "src" in attrs:
            self.external.append(attrs["src"])

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_data = False
            self.in_controller = False

    def handle_data(self, data):
        if self.in_data:
            self.data += data
        if self.in_controller:
            self.controller += data


def test_report_names_cannot_escape_the_embedded_json():
    module = importlib.import_module("evolution_sim.experiments.dashboard")
    report = {
        "name": '</script><script src="https://malicious.invalid"></script>',
        "description": "<img src=x onerror=alert(1)> & Unicode 🌱",
    }
    page = module.render_dashboard(report)
    parser = EvidenceParser()
    parser.feed(page)
    assert json.loads(parser.data) == report
    assert len(parser.scripts) == 2  # data and local controller, no injected third script
    assert parser.external == []


@pytest.mark.parametrize("points", [2, 125_000])
def test_renderer_keeps_skewed_means_inside_axis_without_argument_overflow(points):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is optional for the JavaScript renderer regression")
    module = importlib.import_module("evolution_sim.experiments.dashboard")
    parser = EvidenceParser()
    parser.feed(module.render_dashboard({}))
    # Execute the actual page controller with a tiny deterministic DOM adapter.
    # Dropping the mean from the ceiling clips y<0; spreading 250k values crashes V8.
    harness = r"""
const nodes=new Map();
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.attrs={};this.style={};this.value="";this.textContent=""}
 appendChild(node){this.children.push(node);return node}
 setAttribute(k,v){this.attrs[k]=String(v);if(k==="id")nodes.set(String(v),this)}
 getAttribute(k){return this.attrs[k]}
 addEventListener(){}
 replaceChildren(){this.children=[]}
 get childElementCount(){return this.children.length}
 getBoundingClientRect(){return {left:0,width:1000}}
 get clientWidth(){return 1000}
 classList={add(){}};
}
const document={
 getElementById(id){if(!nodes.has(id))nodes.set(id,new Element("div"));return nodes.get(id)},
 createElement:t=>new Element(t),createElementNS:(ns,t)=>new Element(t)
};
const n=POINT_COUNT;
const point=i=>({tick:i,population:{mean:12.5,q25:0,q75:0,replicates:8}});
const fixture={
 protocol:{name:"Axis fixture",description:"Renderer test",ticks:n-1,seeds:[1],
  control:"baseline",bootstrap_samples:100,arms:[
   {id:"baseline",label:"Control",events:[]},{id:"treatment",label:"Treatment",events:[]}]},
 invariant_failure_replicates:0,execution_failure_replicates:0,
 replicates:[],caveats:[],provenance:{},trajectory_bands:{
  baseline:Array.from({length:n},(_,i)=>point(i)),
  treatment:Array.from({length:n},(_,i)=>point(i))},
 contrasts:[{arm:"treatment",effects:{mean_population:{pairs:1,available_pairs:1,
  mean_difference:0,standard_error:null,bootstrap_percentile_95:null,differences:[0]}}}]
};
document.getElementById("evidence").textContent=JSON.stringify(fixture);
document.getElementById("measure").value="population";
document.getElementById("effect-arm").value="treatment";
""".replace("POINT_COUNT", str(points))
    assertions = r"""
const paths=nodes.get("trajectory").children.filter(n=>n.tag==="polyline");
if(paths.length!==2)throw Error("missing mean paths");
for(const p of paths)for(const xy of p.attrs.points.split(" ")){
 const y=Number(xy.split(",")[1]);if(y<42||y>350)throw Error("mean clipped outside plot")
}
console.log("axis and large report pass");
"""
    result = subprocess.run(
        [node],
        input=harness + parser.controller + assertions,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
