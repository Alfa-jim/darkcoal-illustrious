(function(root){
  'use strict';
  const CHECKPOINTS=Object.freeze({shirea:'illustriousShirea2D_v10.safetensors',nxt:'illustriousnxtXLBy_v20.safetensors',base:'Illustrious-XL-v2.0.safetensors'});
  const DMD2_FILE='HerrscherAGGA2026_DMD2_BTN_V75_FIX.safetensors';
  function checkpointFile(choice='shirea'){
    if(!Object.prototype.hasOwnProperty.call(CHECKPOINTS,choice)) throw new Error('Unknown checkpoint');
    return CHECKPOINTS[choice];
  }
  function selectedLoras(custom,enabled,strength){
    if(!enabled) return custom.slice();
    const w=Number(strength);
    if(!Number.isFinite(w)||w<0||w>2) throw new Error('DMD2 strength must be between 0 and 2');
    if(custom.some(l=>l.name.replace(/\.safetensors$/,'')===DMD2_FILE.replace(/\.safetensors$/,''))) throw new Error('Duplicate DMD2 LoRA: use its dedicated control');
    return [{name:DMD2_FILE,w},...custom];
  }
  const api={CHECKPOINTS,DMD2_FILE,checkpointFile,selectedLoras};
  if(typeof module!=='undefined'&&module.exports) module.exports=api;
  else root.IllustriousModels=api;
})(globalThis);
