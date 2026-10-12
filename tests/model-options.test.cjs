const {test}=require('node:test');
const assert=require('node:assert/strict');
const models=require('../model-options.js');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../playground.html'),'utf8');
function extract(name){
  const start=html.indexOf('function '+name+'(');
  const end=html.indexOf('\nfunction ',start+1);
  return html.slice(start,end);
}
function context(){
  const elements={};
  for(const [id,value] of Object.entries({checkpoint:'shirea',steps:'28',cfg:'6.5',sampler:'euler_ancestral',scheduler:'normal',width:'1024',height:'1024',seed:'42',batch:'1',dmd2Strength:'1'})) elements[id]={value};
  const ctx=vm.createContext({IllustriousModels:models,mode:'txt2img',refs:[],getLoras:()=>[],log:()=>{},addLora:()=>{},clearLoras:()=>{},$:id=>elements[id]||=( {value:'',checked:false} )});
  return {ctx,elements};
}
test('real playground workflow selects either checkpoint with optional DMD2 conditioning',()=>{
  const {ctx,elements}=context();
  vm.runInContext(extract('buildWorkflow'),ctx);
  for(const choice of ['shirea','nxt']){
    elements.checkpoint.value=choice;
    elements.useDmd2={checked:false};
    let graph=vm.runInContext('buildWorkflow()',ctx);
    assert.equal(graph['30'].inputs.ckpt_name,models.checkpointFile(choice));
    assert.equal(graph['31'].inputs.steps,28);
    assert.equal(graph['100'],undefined);
    elements.useDmd2.checked=true;
    graph=vm.runInContext('buildWorkflow()',ctx);
    assert.equal(graph['100'].inputs.lora_name,models.DMD2_FILE);
    assert.deepEqual(Array.from(graph['31'].inputs.model),['100',0]);
    assert.deepEqual(Array.from(graph['6'].inputs.clip),['100',1]);
    assert.deepEqual(Array.from(graph['8'].inputs.vae),['30',2]);
  }
});
test('DMD2 preset enables new LoRA and uses explicit starting settings',()=>{
  const {ctx,elements}=context();
  vm.runInContext(extract('preset'),ctx);
  vm.runInContext("preset('turbo')",ctx);
  assert.equal(elements.useDmd2.checked,true);
  assert.equal(Number(elements.steps.value),6);
  assert.equal(Number(elements.cfg.value),1);
  assert.equal(elements.sampler.value,'euler');
});
test('image references use registered IPAdapter nodes without a hidden browser flag',()=>{
  const {ctx,elements}=context();
  ctx.refs=[{name:'reference.png'}];
  elements.useIPAdapter={checked:true};
  vm.runInContext(extract('buildWorkflow'),ctx);
  const graph=vm.runInContext('buildWorkflow()',ctx);
  assert.equal(graph['72']?.class_type,'IPAdapterModelLoader');
  assert.equal(graph['73']?.class_type,'IPAdapterAdvanced');
  assert.deepEqual(Array.from(graph['31'].inputs.model),['73',0]);
});
test('checkpoint selection uses exact filenames and rejects arbitrary paths',()=>{
  assert.equal(models.checkpointFile(), 'illustriousShirea2D_v10.safetensors');
  assert.equal(models.checkpointFile('nxt'), 'illustriousnxtXLBy_v20.safetensors');
  assert.equal(models.checkpointFile('base'), 'Illustrious-XL-v2.0.safetensors');
  assert.throws(()=>models.checkpointFile('../other'), /Unknown checkpoint/);
});
test('DMD2 is optional, preserves custom LoRAs and validates strength',()=>{
  const custom=[{name:'details',w:0.5}];
  assert.deepEqual(models.selectedLoras(custom,false,1),custom);
  const enabled=models.selectedLoras(custom,true,0.8);
  assert.equal(enabled[0].name,models.DMD2_FILE);
  assert.equal(enabled[0].w,0.8);
  assert.deepEqual(enabled[1],custom[0]);
  assert.equal(custom.length,1);
  assert.throws(()=>models.selectedLoras([],true,NaN),/strength/);
  assert.throws(()=>models.selectedLoras([{name:models.DMD2_FILE,w:1}],true,1),/duplicate/i);
});
