/* Optional browser smoke test: npm install --no-save playwright && npx playwright install chromium
 * Run: node tests/browser.cjs
 * Set CHROMIUM_PACKAGE to an absolute @sparticuz/chromium package directory if needed.
 */
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const {mkdtempSync, rmSync, mkdirSync} = require('node:fs');
const {tmpdir} = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');

(async()=>{
  const root=path.resolve(__dirname,'..');
  const data=mkdtempSync(path.join(tmpdir(),'quizspark-ui-'));
  const out=process.env.SCREENSHOT_DIR||path.join(root,'test-results');
  mkdirSync(out,{recursive:true});
  const password='temporary-browser-test-password';
  const server=spawn(process.env.PYTHON||'python',['app/server.py'],{cwd:root,env:{...process.env,DATA_DIR:data,ADMIN_PASSWORD:password,PORT:'8765',PYTHONUNBUFFERED:'1'},stdio:['ignore','pipe','pipe']});
  let logs='';server.stdout.on('data',b=>logs+=b);server.stderr.on('data',b=>logs+=b);
  let browser;
  const errors=[];
  try {
    let ready=false;
    for(let i=0;i<100;i++){try{await fetch('http://127.0.0.1:8765/health');ready=true;break;}catch{await new Promise(r=>setTimeout(r,100));}}
    assert.ok(ready,'Server did not start: '+logs);
    let launch={headless:true};
    if(process.env.CHROMIUM_PACKAGE){const binary=require(path.join(process.env.CHROMIUM_PACKAGE,'build/index.js')).default;launch={...launch,executablePath:process.env.CHROMIUM_EXECUTABLE||await binary.executablePath(),args:binary.args};}
    browser=await chromium.launch(launch);
    const hostContext=await browser.newContext({viewport:{width:1440,height:1000},locale:'th-TH'});
    const playerContext=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    const host=await hostContext.newPage(),player=await playerContext.newPage();
    for(const page of [host,player])page.on('pageerror',e=>errors.push(e.message));
    await host.goto('http://127.0.0.1:8765/');
    await host.locator('#quick-pin').waitFor();
    await host.evaluate(()=>document.fonts.ready);
    await host.screenshot({path:path.join(out,'home-th.png'),fullPage:true,animations:"disabled"});
    await host.locator('[data-action="language"]').click();
    await host.locator('[data-action="manager"]').click();
    await host.locator('#host-password').fill(password);
    await host.locator('#login-form button[type="submit"]').click();
    await host.locator('[data-action="new"]').click();
    await host.locator('[data-draft="title"]').fill('Browser integration');
    await host.locator('[data-draft="category"]').fill('Smoke test');
    await host.locator('[data-field="text"]').fill('2 + 2?');
    for(let i=0;i<4;i++)await host.locator(`[data-option="${i}"]`).fill(String(i+2));
    await host.locator('[data-correct="2"]').check();
    await host.locator('[data-field="time"]').fill('20');
    await host.locator('[data-field="explanationText"]').fill('Four is correct.');
    // Create a valid PNG with Pillow; do not rely on a potentially corrupt sample.
    const imagePath=path.join(data,'test.png');
    await new Promise((resolve,reject)=>{const p=spawn(process.env.PYTHON||'python',['-c','from PIL import Image; import sys; Image.new("RGB", (120,80), "purple").save(sys.argv[1])',imagePath]);p.on('close',code=>code?reject(Error('image setup')):resolve());});
    await host.locator('[data-upload="image"]').setInputFiles(imagePath);
    await host.waitForFunction(()=>document.querySelector('[data-field="image"]').value.startsWith('/uploads/'));
    await host.locator('[data-action="add-question"]').click();
    await host.locator('[data-field="type"]').selectOption('open');
    await host.locator('[data-field="text"]').fill('Gold symbol?');
    await host.locator('[data-field="openAnswers"]').fill('Au');
    await host.locator('[data-field="time"]').fill('20');
    await host.screenshot({path:path.join(out,'editor-en.png'),fullPage:true,animations:"disabled"});
    await host.locator('[data-action="save"]').click();
    const card=host.locator('.quiz-card').filter({hasText:'Browser integration'});
    await card.locator('[data-action="host-quiz"]').click();
    await host.locator('.lobby-pin').waitFor();
    const pin=(await host.locator('.lobby-pin').innerText()).trim();
    await player.goto('http://127.0.0.1:8765/?pin='+pin);
    await player.locator('#nickname').fill('Mobile player');
    await player.locator('[data-avatar="🐼"]').click();
    await player.locator('#player-join button[type="submit"]').click();
    await host.locator('.player-tile').waitFor();
    await host.screenshot({path:path.join(out,'lobby-en.png'),fullPage:true,animations:"disabled"});
    await host.locator('[data-action="start"]').click();
    await player.locator('[data-action="answer"]').first().waitFor();
    await player.screenshot({path:path.join(out,'player-mobile.png'),fullPage:true,animations:"disabled"});
    await player.locator('[data-action="answer"][data-index="2"]').click();
    await player.locator('.feedback').waitFor();
    assert.equal(await player.locator('.feedback.wrong').count(),0,'Correct answer marked wrong');
    await host.locator('[data-action="leaderboard"]').click();
    await host.locator('[data-action="next"]').click();
    await player.locator('#answer-text').fill('Au');
    await player.reload();
    await player.locator('#answer-text').waitFor();
    await player.locator('#answer-text').fill(' au ');
    await player.locator('#open-answer button').click();
    await player.locator('.feedback').waitFor();
    assert.equal(await player.locator('.feedback.wrong').count(),0);
    await host.locator('[data-action="leaderboard"]').click();
    await host.locator('[data-action="next"]').click();
    await player.locator('.podium').waitFor();
    await host.screenshot({path:path.join(out,'podium-en.png'),fullPage:true,animations:"disabled"});
    await player.locator('[data-action="leave"]').click();
    await player.locator('#quick-pin').waitFor();
    const overflow=await player.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
    assert.equal(overflow,false,'Mobile layout overflows horizontally');
    await host.locator('[data-action="new-game"]').click();
    await host.locator('[data-action="home"]').last().click();
    await host.locator('[data-action="simulator"]').click();
    await host.locator('.simulator iframe').first().waitFor();
    await host.frameLocator('.simulator iframe').first().locator('.quiz-card').first().waitFor();
    await host.frameLocator('#player-frame').locator('#player-pin').waitFor();
    assert.deepEqual(errors,[],'Browser errors');
    console.log('PASS: editor + image upload, host login, mobile MCQ/open, player refresh, scoreboard/podium, simulator, no JS errors.');
    console.log('Browser:',browser.version());
    console.log('Screenshots:',out);
  } finally {
    if(browser)await browser.close();
    server.kill('SIGTERM');
    await new Promise(resolve=>server.on('close',resolve));
    rmSync(data,{recursive:true,force:true});
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
