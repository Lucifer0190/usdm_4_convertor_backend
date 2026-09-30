"""Run the official CDISC CORE gate on delivered studies; print per-rule results."""
import sys, glob, os, json, collections, time
sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv(".env")
from usdm4 import USDM4
run = sys.argv[1]
out = {}
for p in sorted(glob.glob(f"{run}/*/study.usdm.json")):
    st = os.path.basename(os.path.dirname(p)); t = time.time()
    try:
        r = USDM4().validate_core(p)
        out[st] = {"valid": r.is_valid, "rules_executed": r.rules_executed, "rules_skipped": r.rules_skipped,
                   "finding_count": r.finding_count, "execution_errors": r.execution_error_count,
                   "ct_available": r.ct_packages_available, "ct_loaded": len(r.ct_packages_loaded),
                   "secs": round(time.time() - t),
                   "findings": [{"rule_id": f.rule_id, "description": f.description, "message": f.message,
                                 "n": f.error_count, "sample": f.errors[:2]} for f in r.findings]}
        v = out[st]
        print(st, "valid", v["valid"], "executed", v["rules_executed"], "findings", v["finding_count"],
              "rules_with_findings", len(v["findings"]), "exec_errors", v["execution_errors"],
              "ct", v["ct_loaded"], f"{v['secs']}s", flush=True)
    except Exception as e:
        out[st] = {"error": str(e)[:400]}; print(st, "ERROR", str(e)[:300], flush=True)
json.dump(out, open(f"{run}/core_results.json", "w"), indent=1, default=str)
by = collections.defaultdict(lambda: {"n": 0, "studies": set(), "msg": "", "desc": ""})
for st, v in out.items():
    for f in v.get("findings", []):
        b = by[f["rule_id"]]; b["n"] += f["n"]; b["studies"].add(st); b["msg"] = f["message"]; b["desc"] = f["description"]
for rid, b in sorted(by.items()):
    print(f"== {rid} studies={len(b['studies'])} findings={b['n']}")
    print("   ", (b["desc"] or "")[:220])
    print("   ", (b["msg"] or "")[:200])
