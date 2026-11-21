"""One final text assembly for compliance, copy/export and official upload."""
import re


def publication_text(meta, platform):
    field='caption' if platform=='tiktok' else 'description'
    text=str(meta.get(field) or meta.get('description') or '')
    # Metadata retains exact mandatory phrases. Append only absent whole tokens.
    missing=[tag for tag in meta.get('hashtags',[]) if not re.search(r'(?<!\w)'+re.escape(tag)+r'(?!\w)',text,re.I)]
    return (text+('\n\n'+' '.join(missing) if missing else '')).strip()
