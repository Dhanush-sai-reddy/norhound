import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.run_ats_jobs_connector as m

OLD_ATS = re.compile(
    r"https?://(?:"
    r"(?P<workday>[a-z0-9-]+)\.wd(?P<wdn>\d+)\.myworkdayjobs\.com/(?P<wdsite>[A-Za-z0-9_-]+)"
    r"|jobs\.lever\.co/(?P<lever>[A-Za-z0-9-]+)"
    r"|boards\.greenhouse\.io/(?P<greenhouse>[A-Za-z0-9-]+)"
    r"|job-boards\.greenhouse\.io/(?P<greenhouse2>[A-Za-z0-9-]+)"
    r"|(?P<smart>[A-Za-z0-9-]+)\.smartrecruiters\.com"
    r"|(?P<teamtailor>[A-Za-z0-9-]+)\.teamtailor\.com"
    r")", re.I)

mode = sys.argv[1]
if mode == "old":
    m.ATS_PATTERN = OLD_ATS
    m.LINKED_ATS_PROVIDERS = ()
    m.collect_careers_page_links = lambda *a, **k: []
sys.argv = ["ats_ab", "--profiles", "out/web1000-profiles.jsonl",
            "--output", f"out/ats-ab-{mode}.jsonl", "--report", f"out/ats-ab-{mode}.json",
            "--limit", "80", "--workers", "12"]
m.main()
