import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const out = process.argv[2] || 'ab-output';
await fs.mkdir(out, {recursive:true});
const targetA = 'https://stateofaidesign.com/';
const candidateUrl = process.env.CANDIDATE_URL || 'http://127.0.0.1:4173/';
const baselineUrl = (process.env.BASELINE_URL || '').trim() || null;
const viewports = [
  {name:'desktop', width:1440, height:1000},
  {name:'mobile', width:412, height:915},
];
const checkpoints = [
  {name:'hero', a:null, b:'#hero'},
  {name:'intro', a:{kind:'text', text:'In 2025, designers were experimenting with AI'}, b:'#intro h1'},
  {name:'quote', a:{kind:'text', text:'AI is sparking a creative renaissance'}, b:'#quote blockquote'},
  {name:'tools', a:{kind:'text', text:'The great toolstack shakeup'}, b:'#tools h2'},
  {name:'cases', a:{kind:'text', text:'Seven companies. Seven ways of navigating the same shift'}, b:'#cases h2'},
  {name:'newsletter', a:{kind:'text', text:'Get new case studies'}, b:'#newsletter h2'},
];

const browser = await chromium.launch({headless:true});
async function waitForTextStability(page, {maxMs=12000, stableMs=1500, intervalMs=250}={}) {
  const started = Date.now();
  let previous = '';
  let stableSince = 0;
  let samples = 0;
  while (Date.now() - started <= maxMs) {
    const current = await page.evaluate(() => (document.body?.innerText || '').replace(/\s+/g, ' ').trim());
    samples += 1;
    if (current && current === previous) {
      if (!stableSince) stableSince = Date.now();
      if (Date.now() - stableSince >= stableMs) return {stable:true, elapsedMs:Date.now()-started, samples};
    } else {
      previous = current;
      stableSince = 0;
    }
    await page.waitForTimeout(intervalMs);
  }
  return {stable:false, elapsedMs:Date.now()-started, samples};
}
async function prepare(page, url, isTarget=false) {
  await page.goto(url, {waitUntil:'domcontentloaded', timeout:90000});
  await page.evaluate(async () => { if (document.fonts?.ready) await document.fonts.ready; });
  await page.waitForTimeout(isTarget ? 500 : 250);
  const stability = await waitForTextStability(page);
  if (!stability.stable) throw new Error(`text did not stabilize for ${url} within ${stability.elapsedMs}ms`);
  await page.addStyleTag({content:'*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important;}'}).catch(()=>{});
  await page.waitForTimeout(250);
  return stability;
}
async function move(page, spec) {
  if (!spec) { await page.evaluate(()=>scrollTo(0,0)); return; }
  let loc;
  if (typeof spec === 'string') loc = page.locator(spec).first();
  else loc = page.getByText(spec.text, {exact:false}).first();
  await loc.waitFor({state:'attached', timeout:30000});
  await loc.evaluate(el => {
    const y = el.getBoundingClientRect().top + window.scrollY - 40;
    window.scrollTo(0, Math.max(0,y));
  });
  await page.waitForTimeout(300);
}

const captureMeta = {
  schema:'awwwards-ab-capture-v3',
  mode: baselineUrl ? 'candidate-vs-main-same-reference' : 'single-candidate',
  targetA,
  candidateUrl,
  baselineUrl,
  viewports:{}
};
for (const vp of viewports) {
  const ctx = await browser.newContext({viewport:{width:vp.width,height:vp.height}, reducedMotion:'reduce', colorScheme:'light'});
  const a = await ctx.newPage();
  const b = await ctx.newPage();
  const base = baselineUrl ? await ctx.newPage() : null;
  const aStability = await prepare(a,targetA,true);
  const bStability = await prepare(b,candidateUrl,false);
  const baseStability = base ? await prepare(base,baselineUrl,false) : null;
  captureMeta.viewports[vp.name] = {targetA:aStability,candidateB:bStability,baselineMain:baseStability,checkpoints:{}};
  for (const cp of checkpoints) {
    await move(a,cp.a);
    await move(b,cp.b);
    if (base) await move(base,cp.b);
    const aCheckpoint = await waitForTextStability(a,{maxMs:10000,stableMs:1200,intervalMs:200});
    const bCheckpoint = await waitForTextStability(b,{maxMs:5000,stableMs:800,intervalMs:200});
    const baseCheckpoint = base ? await waitForTextStability(base,{maxMs:5000,stableMs:800,intervalMs:200}) : null;
    if (!aCheckpoint.stable || !bCheckpoint.stable || (baseCheckpoint && !baseCheckpoint.stable)) {
      throw new Error(`checkpoint text did not stabilize: ${vp.name}/${cp.name}`);
    }
    captureMeta.viewports[vp.name].checkpoints[cp.name] = {targetA:aCheckpoint,candidateB:bCheckpoint,baselineMain:baseCheckpoint};
    // A is captured once and reused for both candidate and baseline scoring.
    await a.screenshot({path:path.join(out,`${vp.name}-${cp.name}-A.png`), fullPage:false});
    await b.screenshot({path:path.join(out,`${vp.name}-${cp.name}-B.png`), fullPage:false});
    if (base) await base.screenshot({path:path.join(out,`${vp.name}-${cp.name}-BASE.png`), fullPage:false});
  }
  await ctx.close();
}
await fs.writeFile(path.join(out,'capture-meta.json'), JSON.stringify(captureMeta,null,2)+'\n');
await browser.close();
