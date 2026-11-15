"""Load the demo found items and two lost reports.

Cost: one gpt-4o-mini vision call (low detail) per photo; CLIP runs locally.

    python seed.py                       # local catalog 'lostfound'
    python seed.py pxt://<your-org>:<your-db>
"""

from __future__ import annotations

import sys
from pathlib import Path

from app import Clips, Found, LostReports, TableModel

TARGET = sys.argv[1] if len(sys.argv) > 1 else 'lostfound'
DATA = Path(__file__).parent / 'data'

FOUND = [
    ('keys.jpg', 'Elm St bus shelter', '2026-11-10', 'Dana'),
    ('wallet.jpg', 'Corner cafe, window seat', '2026-11-11', 'cafe staff'),
    ('teddy.jpg', 'Playground sandbox', '2026-11-09', None),
    ('glove.jpg', 'Fence post on Oak Ave', '2026-11-12', 'Sam'),
    ('scarf.jpg', 'Library reading room', '2026-11-12', 'library desk'),
    ('headphones.jpg', 'Gym locker room bench', '2026-11-13', None),
    ('water_bottle.jpg', 'Soccer field bleachers', '2026-11-08', 'coach Lee'),
    ('umbrella.png', 'Train platform 2', '2026-11-13', None),
]
CLIPS = [
    ('bike-at-park-gate.mp4', 'Park gate, north entrance', 'Mo'),
    ('backpack-bus-stop.mp4', 'Bus stop on 5th', None),
]
LOST = [
    {'description': 'black leather wallet', 'lost_near': 'cafe', 'contact': 'reply on the board'},
    {'description': 'a set of keys on a metal ring', 'lost_near': 'Elm St', 'contact': None},
]

if __name__ == '__main__':
    TableModel.bind_all(TARGET)
    print(Found.insert(
        [{'photo': str(DATA / 'photos' / f), 'spot': s, 'found_on': d, 'finder': who, 'status': 'open'} for f, s, d, who in FOUND],
        on_error='ignore',
    ))
    print(Clips.insert([{'video': str(DATA / 'clips' / f), 'spot': s, 'finder': who} for f, s, who in CLIPS], on_error='ignore'))
    for row in Found.select(Found.spot, Found.color, Found.caption).collect():
        print(f"- {row['spot']}: [{row['color']}] {row['caption']}")
    print(LostReports.insert(LOST, on_error='ignore'))
    for row in LostReports.select(LostReports.description, LostReports.matches).collect():
        print('lost:', row['description'], '->', [(m['spot'], m['score']) for m in row['matches']])
