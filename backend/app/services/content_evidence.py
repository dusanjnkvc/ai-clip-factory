"""Conservative exclusion of clearly described non-scene samples."""
import re


def scene_observation(text):
    value=str(text).strip()
    if not value or re.search(r'\b(?:title card|rating label|menu panel|loading screen|credits|uniformly black|no visible content|no identifiable original scene)\b',value,re.I):return False
    return not (re.search(r'\b(?:text|letters|logo)\b',value,re.I) and re.search(r'\b(?:black background|background is black|blank background)\b',value,re.I))
