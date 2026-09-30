"""Per-rule d4k failures (message, class, attribute, count, sample path) over a run dir."""
import sys, glob, os, collections, json
sys.path.insert(0, "src")
from usdm4 import USDM4
run = sys.argv[1]
by_rule = collections.defaultdict(lambda: {"studies": set(), "n": 0, "msgs": collections.Counter(), "text": "", "samples": []})
for p in sorted(glob.glob(f"{run}/*/study.usdm.json")):
    st = os.path.basename(os.path.dirname(p))
    for f in USDM4().validate(p).to_dict():
        if f.get("status") != "Failure":
            continue
        b = by_rule[f["rule_id"]]
        b["studies"].add(st); b["n"] += 1
        b["msgs"][f"{f.get('klass')}.{f.get('attribute')}: {f.get('message')}"] += 1
        b["text"] = f.get("rule_text", "")
        if len(b["samples"]) < 2:
            b["samples"].append(f"{st} {f.get('path')}")
for rid in sorted(by_rule):
    b = by_rule[rid]
    print(f"== {rid}  studies={len(b['studies'])}  findings={b['n']}")
    print("   RULE:", b["text"][:260])
    for m, c in b["msgs"].most_common(3):
        print(f"   {c}x {m[:200]}")
    for s in b["samples"]:
        print("   e.g.", s)
