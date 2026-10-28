path = r'D:\dev\tms\src\tms\templates\monitor.html'
with open(path, 'r', encoding='utf-8') as f:
    s = f.read()
s = s.replace(\"const res = await fetch('/api/monitor');\", \"const res = await fetch('/api/monitor?stored=true');\")
with open(path, 'w', encoding='utf-8') as f:
    f.write(s)
print('ok')
