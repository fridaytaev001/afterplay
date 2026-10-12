import os,sys,time,json,subprocess,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
env={**os.environ,"OFFLINE":"1","PORT":"18765","DATA_PATH":str(Path(tempfile.mkdtemp())/"ui.sqlite")}
artifacts=Path(tempfile.mkdtemp(prefix="afterplay-browser-"))
log=open(artifacts/"ui.log","w")
proc=subprocess.Popen([sys.executable,str(root/"app.py")],env=env,stdout=log,stderr=log)
try:
    from urllib.request import urlopen
    for _ in range(50):
        try:
            urlopen("http://127.0.0.1:18765/api/health",timeout=1);break
        except Exception:time.sleep(.1)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=["--no-sandbox"])
        page=browser.new_page(viewport={"width":1440,"height":1050})
        errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto("http://127.0.0.1:18765")
        page.wait_for_function("document.getElementById('connection').textContent.includes('OFFLINE')")
        assert page.locator("#board .cell").count()==81
        assert page.locator("#benchmark").is_disabled()
        page.get_by_role("button",name="Square E2, legal move",exact=True).click()
        page.wait_for_function("document.getElementById('decision-source').textContent==='OFFLINE'")
        assert page.locator("#turn").inner_text()=="Your turn"
        page.get_by_role("button",name="Horizontal wall",exact=True).click()
        assert page.locator(".wall-target").count()==64
        page.locator(".wall-target").first.click()
        page.wait_for_function("document.getElementById('your-walls').textContent==='9 walls'")
        page.wait_for_function("document.getElementById('turn').textContent==='Your turn'")
        page.locator("#save-round").click()
        page.wait_for_function("document.getElementById('saved-count').textContent==='1'")
        assert "unfinished" in page.locator("#memory").inner_text()
        page.locator("#compare").click()
        page.wait_for_selector(".comparison-card")
        page.wait_for_function("!document.getElementById('compare').disabled")
        assert page.locator(".comparison-card").count()==4
        page.get_by_role("button",name="Highlight move").first.click()
        assert page.locator(".preview-move,.preview-wall").count()>0
        page.screenshot(path=str(artifacts/"desktop.png"),full_page=True)
        page.set_viewport_size({"width":390,"height":844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(artifacts/"mobile.png"),full_page=True)
        assert not errors,errors
        browser.close()
        print(json.dumps({"browser_checks":"passed","desktop":1440,"mobile":390,"js_errors":errors}))
finally:
    proc.terminate();proc.wait(timeout=5);log.close()
