"""Record installed package metadata without importing third-party code."""
import json
from importlib.metadata import distributions
from pathlib import Path

root = Path(__file__).resolve().parents[1]
items = []
for dist in distributions():
    meta = dist.metadata
    items.append({'name': meta['Name'], 'version': dist.version,
        'license': meta.get('License-Expression') or meta.get('License') or 'See bundled license files',
        'license_files': [str(p) for p in dist.files or [] if 'license' in str(p).lower() or 'copying' in str(p).lower()],
        'license_classifiers': [v for v in meta.get_all('Classifier', []) if 'License' in v]})
target = root / 'docs' / 'python-license-inventory.json'
target.write_text(json.dumps(sorted(items, key=lambda i: i['name'].lower()), indent=2), encoding='utf-8')
print(f'Recorded {len(items)} installed distributions in {target}')
