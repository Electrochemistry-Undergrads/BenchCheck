const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function workspace() {
  const elements = new Map();
  const element = () => ({disabled:false,hidden:false,textContent:'',innerHTML:'',prepend(){},focus(){},setAttribute(){},classList:{toggle(){}}});
  const sandbox = { structuredClone, FormData, Blob, console,
    document:{querySelector(key){if(!elements.has(key))elements.set(key,element());return elements.get(key)},querySelectorAll(){return []},createElement:element},
    pending:[], queueMicrotask, window:{addEventListener(){}}, CSS:{escape:s=>s} };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync('web/app.js','utf8').replace(/\ninit\(\);\s*$/, ''),sandbox);
  vm.runInContext(`
    api = (_path) => new Promise(resolve => pending.push({path:_path,resolve}));
    showError = () => {}; renderResults = () => {}; updateWorkspace = () => {};
    refreshReport = async () => {}; renderEvidence = () => {};
    state.file = new Blob(['test']); state.fileName='test.csv';
    state.mapping={potential:'E',current:'I',time:null};
  `,sandbox);
  return {sandbox,run:code=>vm.runInContext(code,sandbox)};
}
const result = id=>({analysis_id:id, selected_cycle:1, display:{density:false}, metadata:{}, evidence_plan:[], hypotheses:[]});

test('an older analyze response cannot overwrite a new file or newer analysis', async()=>{
  const {sandbox,run}=workspace();
  const older=run('runAnalysis()');
  run('state.generation++; state.analysisRequest++; state.analysis=null');
  const newer=run('runAnalysis()');
  sandbox.pending[1].resolve(result('new'));
  await newer;
  sandbox.pending[0].resolve(result('old'));
  await older;
  assert.equal(run('state.analysis.analysis_id'),'new');
});

test('draft changes mark results dirty without changing applied settings',()=>{
  const {run}=workspace();
  run('state.analysis={}; state.appliedConfig=structuredClone(buildConfig()); state.metadata.electrode_area_cm2=2');
  assert.equal(run('draftDirty()'),true);
  assert.equal(run('state.appliedConfig.metadata.electrode_area_cm2'),undefined);
  run('state.metadata.electrode_area_cm2=null');
  assert.equal(run('draftDirty()'),false);
});

test('evidence finishing for an old file cannot enter the new evidence state',async()=>{
  const {sandbox,run}=workspace();
  run('state.analysis={analysis_id:"old",metadata:{},evidence_plan:[{id:"q",query:"test"}],hypotheses:[]};');
  const request=run('runEvidence()');
  run('state.analysis=null; state.evidence=freshEvidence()');
  sandbox.pending[0].resolve({log:{status:'cached',ok:true},sources:[]});
  await request;
  assert.equal(run('state.evidence.log.length'),0);
  assert.equal(run('state.evidence.done'),false);
});
