import re
with open('shiroko_out.html', 'r', encoding='utf-8') as f:
    text = f.read()

urls = re.findall(r'href=[\"\'\\]+?([^\"\'\\]+)', text)
print('All URLs:', list(set(urls)))
