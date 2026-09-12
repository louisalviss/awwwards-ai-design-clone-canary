import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const out = process.argv[2] || 'ab-output';
await fs.mkdir(out, {recursive:true});
const targetA = 'https://stateofaidesign.com/';
const targetB = 'http://127.0.0.1:4173/';
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
async function prepare(page, url) {
  await page.goto(url, {waitUntil:'domcontentloaded', timeout:90000});
  await page.waitForTimeout(url === targetA ? 4500 : 800);
  await page.addStyleTag({content:'*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important;}'}).catch(()=>{});
  await page.waitForTimeout(250);
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
for (const vp of viewports) {
  const ctx = await browser.newContext({viewport:{width:vp.width,height:vp.height}, reducedMotion:'reduce', colorScheme:'light'});
  const a = await ctx.newPage();
  const b = await ctx.newPage();
  await prepare(a,targetA); await prepare(b,targetB);
  for (const cp of checkpoints) {
    await move(a,cp.a); await move(b,cp.b);
    await a.screenshot({path:path.join(out,`${vp.name}-${cp.name}-A.png`), fullPage:false});
    await b.screenshot({path:path.join(out,`${vp.name}-${cp.name}-B.png`), fullPage:false});
  }
  await ctx.close();
}
await browser.close();
