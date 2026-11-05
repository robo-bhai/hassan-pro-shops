// variants: full | crop | crop@T (scale so line height ~T)
const fs=require('fs'),path=require('path');
const [,,modPath,dataDir,outDir,targets]=process.argv; const P=require(modPath); fs.mkdirSync(outDir,{recursive:true});
const meta=JSON.parse(fs.readFileSync(path.join(dataDir,'meta.json')));
function pgm(f,a,w,h){fs.writeFileSync(f,Buffer.concat([Buffer.from(`P5\n${w} ${h}\n255\n`),Buffer.from(a)]));}
function crop(a,w,b){const bw=b.x1-b.x0,bh=b.y1-b.y0,o=new Uint8ClampedArray(bw*bh);for(let y=0;y<bh;y++)for(let x=0;x<bw;x++)o[y*bw+x]=a[(b.y0+y)*w+b.x0+x];return [o,bw,bh];}
function scale(a,w,h,s){ // bilinear
 const nw=Math.max(8,Math.round(w*s)),nh=Math.max(8,Math.round(h*s)),o=new Uint8ClampedArray(nw*nh);
 for(let y=0;y<nh;y++){const sy=Math.min(h-1,(y+.5)/s-.5<0?0:(y+.5)/s-.5),y0=sy|0,y1=Math.min(h-1,y0+1),ty=sy-y0;
  for(let x=0;x<nw;x++){const sx=Math.min(w-1,(x+.5)/s-.5<0?0:(x+.5)/s-.5),x0=sx|0,x1=Math.min(w-1,x0+1),tx=sx-x0;
   o[y*nw+x]=(a[y0*w+x0]*(1-tx)+a[y0*w+x1]*tx)*(1-ty)+(a[y1*w+x0]*(1-tx)+a[y1*w+x1]*tx)*ty+.5;}}
 return [o,nw,nh];}
const T=(targets||'').split(',').filter(Boolean).map(Number);
const info={};
for(const m of meta){
 const px=new Uint8ClampedArray(fs.readFileSync(path.join(dataDir,m.id+'.rgba')));
 const r=P.process(px,m.w,m.h,process.env.OPTS?JSON.parse(process.env.OPTS):undefined);
 const inv=new Uint8ClampedArray(r.st.length);for(let i=0;i<inv.length;i++)inv[i]=255-r.st[i];
 const src={gray:r.st,bin:r.bin,inv:inv};
 info[m.id]={box:r.box,lines:r.box&&r.box.lines,lineH:r.box&&r.box.lineH};
 for(const k in src){
  pgm(path.join(outDir,`${m.id}.${k}.full.pgm`),src[k],m.w,m.h);
  if(r.box){ let [c,cw,ch]=crop(src[k],m.w,r.box); pgm(path.join(outDir,`${m.id}.${k}.crop.pgm`),c,cw,ch);
   for(const t of T){const s=Math.min(1.5,Math.max(0.3,t/r.box.lineH)); const [sc,sw,sh]=scale(c,cw,ch,s); pgm(path.join(outDir,`${m.id}.${k}.crop${t}.pgm`),sc,sw,sh);} }
  else { pgm(path.join(outDir,`${m.id}.${k}.crop.pgm`),src[k],m.w,m.h); for(const t of T) pgm(path.join(outDir,`${m.id}.${k}.crop${t}.pgm`),src[k],m.w,m.h);} }
}
fs.writeFileSync(path.join(outDir,'info.json'),JSON.stringify(info));
const nb=Object.values(info).filter(i=>!i.box).length; console.log('no box:',nb,'of',meta.length);
const fr=Object.values(info).filter(i=>i.box).map(i=>i.box);
console.log('avg crop area share', (fr.reduce((s,b)=>s+(b.x1-b.x0)*(b.y1-b.y0),0)/fr.length/(800*300)).toFixed(2), 'avg lineH', (fr.reduce((s,b)=>s+b.lineH,0)/fr.length).toFixed(1));
