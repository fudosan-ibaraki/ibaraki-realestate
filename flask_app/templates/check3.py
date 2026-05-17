with open('templates/estimate_base.html', encoding='utf-8') as f:
    lines = f.readlines()
print('総行数:', len(lines))
for i, line in enumerate(lines[270:285], 271):
    print(i, repr(line[:80]))