import re

with open('webscrapingai_out.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Extract all links that contain 'api', 'json', or 'search'
links = re.findall(r'(?:href|src|action)=["\']([^"\']+)["\']', html)
interesting_links = set()
for link in links:
    if 'api' in link.lower() or 'json' in link.lower() or 'search' in link.lower() or '/_next/data/' in link.lower():
        interesting_links.add(link)

print("Found interesting links:")
for link in interesting_links:
    print(link)
