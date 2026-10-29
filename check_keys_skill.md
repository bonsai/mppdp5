# Check Keys Skill (mppdp5)
## 目的
保存された API キー、トークン、環境変数を確認し、漏洩リスクを把握する
## 使用方法
```powershell
python -c "
import os, json, pathlib, re
keys = {k: v for k, v in os.environ.items() if any(x in k.lower() for x in ['key','token','secret','password','api','hf_'])}
print('=== ENV KEYS FOUND ===')
for k, v in keys.items():
    masked = v[:4] + '***' if len(v) > 4 else '***'
    print(f'{k}: {masked}')
print()
print('=== FILE SCAN ===')
repo = pathlib.Path(__file__).parent.parent / 'mppdp5'
for f in repo.rglob('*.json') + repo.rglob('.env'):
    if f.exists():
        text = f.read_text(encoding='utf-8', errors='ignore')
        if re.search(r'(api[_-]?key|token|secret|password)', text, re.IGNORECASE):
            print(f'POTENTIAL SECRET: {f.relative_to(repo)}')
"
```
