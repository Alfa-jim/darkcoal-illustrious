const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../playground.html'),'utf8');
for(const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)){
  new vm.Script(match[1],{filename:'playground.html'});
}
new vm.Script(fs.readFileSync(path.join(__dirname,'../model-options.js'),'utf8'),{filename:'model-options.js'});
console.log('Playground scripts parse successfully');
