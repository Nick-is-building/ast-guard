import os
import secrets
import hashlib
import json
import ast
import builtins
import statistics

def get_ast_guard_dir() -> str:
    path = os.path.expanduser("~/.ast-guard")
    os.makedirs(path, exist_ok=True)
    return path

def get_or_create_salt() -> str:
    path = os.path.join(get_ast_guard_dir(), "machine_salt")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                salt = f.read().strip()
                if salt:
                    return salt
        except Exception:
            pass
    salt = secrets.token_hex(32)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(salt)
    except Exception:
        pass
    return salt

def calculate_scan_id(orig_code: str, gen_code: str, salt: str) -> str:
    hasher = hashlib.sha256()
    hasher.update(orig_code.encode("utf-8"))
    hasher.update(gen_code.encode("utf-8"))
    hasher.update(salt.encode("utf-8"))
    return hasher.hexdigest()

def calculate_fingerprint(gen_code: str, gen_metrics: dict) -> str:
    node_types = {}
    builtin_names = set()
    
    try:
        tree = ast.parse(gen_code)
        for node in ast.walk(tree):
            t_name = type(node).__name__
            node_types[t_name] = node_types.get(t_name, 0) + 1
            
            if isinstance(node, ast.Name):
                if hasattr(builtins, node.id):
                    builtin_names.add(node.id)
    except Exception:
        pass
        
    node_types_sorted = sorted(node_types.items())
    builtins_sorted = sorted(list(builtin_names))
    
    metrics_clean = {}
    for k, v in gen_metrics.items():
        if isinstance(v, list):
            try:
                metrics_clean[k] = sorted(v)
            except TypeError:
                metrics_clean[k] = sorted(v, key=lambda x: json.dumps(x, sort_keys=True, default=str))
        else:
            metrics_clean[k] = v
            
    fingerprint_data = {
        "metrics": metrics_clean,
        "node_types": node_types_sorted,
        "builtins": builtins_sorted
    }
    
    data_str = json.dumps(fingerprint_data, sort_keys=True)
    return hashlib.sha256(data_str.encode("utf-8")).hexdigest()

def log_scan(orig_code: str, gen_code: str, orig_metrics: dict, gen_metrics: dict, check_results: dict, transformations: list, mode: str, verdict: str) -> dict:
    salt = get_or_create_salt()
    scan_id = calculate_scan_id(orig_code, gen_code, salt)
    fingerprint = calculate_fingerprint(gen_code, gen_metrics)
    
    record = {
        "scan_id": scan_id,
        "metrics_fingerprint": fingerprint,
        "mode": mode,
        "verdict": verdict,
        "orig_metrics": {k: v for k, v in orig_metrics.items() if k not in ("import_list", "call_list")},
        "gen_metrics": {k: v for k, v in gen_metrics.items() if k not in ("import_list", "call_list")},
        "check_results": {k: v["status"] for k, v in check_results.items()},
        "transformations": [t["category"] for t in transformations]
    }
    
    path = os.path.join(get_ast_guard_dir(), "telemetry.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass
        
    return record

def add_feedback(scan_id: str, label: str, comment: str = "") -> bool:
    path = os.path.join(get_ast_guard_dir(), "feedback.jsonl")
    record = {
        "scan_id": scan_id,
        "label": label,
        "comment": comment
    }
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return True
    except Exception:
        return False

def export_telemetry(target_path: str) -> bool:
    source_path = os.path.join(get_ast_guard_dir(), "telemetry.jsonl")
    if not os.path.exists(source_path):
        return False
        
    try:
        with open(source_path, "r", encoding="utf-8") as sf, open(target_path, "w", encoding="utf-8") as df:
            for line in sf:
                if not line.strip():
                    continue
                record = json.loads(line)
                # Anonymize scan_id for privacy
                if "scan_id" in record:
                    del record["scan_id"]
                df.write(json.dumps(record) + "\n")
        return True
    except Exception:
        return False

def get_stats() -> dict:
    source_path = os.path.join(get_ast_guard_dir(), "telemetry.jsonl")
    stats = {
        "total_scans": 0,
        "verdicts": {"CLEAN": 0, "WARNING": 0, "CRITICAL": 0},
        "checks": {},
        "transformations": {}
    }
    
    if not os.path.exists(source_path):
        return stats
        
    try:
        with open(source_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                stats["total_scans"] += 1
                verdict = record.get("verdict", "UNKNOWN")
                stats["verdicts"][verdict] = stats["verdicts"].get(verdict, 0) + 1
                
                # Check results
                for check_name, status in record.get("check_results", {}).items():
                    if check_name not in stats["checks"]:
                        stats["checks"][check_name] = {"CLEAN": 0, "WARNING": 0, "CRITICAL": 0}
                    stats["checks"][check_name][status] = stats["checks"][check_name].get(status, 0) + 1
                    
                # Transformations
                for t in record.get("transformations", []):
                    stats["transformations"][t] = stats["transformations"].get(t, 0) + 1
    except Exception:
        pass
        
    return stats

DELTA_METRIC_KEYS = (
    "if_count",
    "literal_count",
    "mccabe_complexity",
    "comprehension_count",
    "functional_call_count",
    "long_string_count",
)


def _empty_delta_summary() -> dict:
    return {"count": 0, "mean": None, "median": None, "min": None, "max": None, "stddev": None}


def get_detailed_stats() -> dict:
    """
    Returns a richer breakdown of the local telemetry log than get_stats():

      - total_scans
      - metric_deltas: for each tracked metric, the per-scan delta
        (gen - orig) summarized as count/mean/median/min/max/stddev. Only
        scans where both sides report the metric contribute.
      - check_correlations: how often selected check combinations fire,
        e.g. Check 1+2 kombi, Check 5+2 kombi, Check 5 firing alone vs.
        alongside any other check, and per-check CRITICAL counts.
      - verdicts_by_mode: verdict distribution split per sensitivity mode.
      - transformations: count and percentage of scans where each allowlist
        category was detected.

    Uses only Python's standard library (statistics for mean/median/stdev).
    """
    source_path = os.path.join(get_ast_guard_dir(), "telemetry.jsonl")

    result = {
        "total_scans": 0,
        "metric_deltas": {k: _empty_delta_summary() for k in DELTA_METRIC_KEYS},
        "check_correlations": {
            "check_1_and_2_kombi": 0,
            "check_5_and_2_kombi": 0,
            "check_5_alone": 0,
            "check_5_with_others": 0,
            "check_3_critical": 0,
            "check_4_critical": 0,
        },
        "verdicts_by_mode": {
            "strict":   {"CLEAN": 0, "WARNING": 0, "CRITICAL": 0},
            "standard": {"CLEAN": 0, "WARNING": 0, "CRITICAL": 0},
            "audit":    {"CLEAN": 0, "WARNING": 0, "CRITICAL": 0},
        },
        "transformations": {},
    }

    if not os.path.exists(source_path):
        return result

    delta_lists = {k: [] for k in DELTA_METRIC_KEYS}
    transformation_counts = {}

    try:
        with open(source_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue

                result["total_scans"] += 1

                # Metric deltas (gen - orig)
                orig_m = record.get("orig_metrics", {}) or {}
                gen_m = record.get("gen_metrics", {}) or {}
                for k in DELTA_METRIC_KEYS:
                    if k in orig_m and k in gen_m:
                        try:
                            delta_lists[k].append(gen_m[k] - orig_m[k])
                        except TypeError:
                            # Non-numeric metric value — skip.
                            continue

                # Check correlations
                cr = record.get("check_results", {}) or {}
                c1 = cr.get("check_1_hardcoding")
                c2 = cr.get("check_2_complexity_collapse")
                c3 = cr.get("check_3_forbidden_calls")
                c4 = cr.get("check_4_import_drift")
                c5 = cr.get("check_5_extensional_enumeration")

                if c1 == "WARNING" and c2 == "WARNING":
                    result["check_correlations"]["check_1_and_2_kombi"] += 1
                if c5 == "WARNING" and c2 == "WARNING":
                    result["check_correlations"]["check_5_and_2_kombi"] += 1
                if c5 == "WARNING":
                    other_fires = any(
                        cr.get(name) in ("WARNING", "CRITICAL")
                        for name in (
                            "check_1_hardcoding",
                            "check_2_complexity_collapse",
                            "check_3_forbidden_calls",
                            "check_4_import_drift",
                        )
                    )
                    if other_fires:
                        result["check_correlations"]["check_5_with_others"] += 1
                    else:
                        result["check_correlations"]["check_5_alone"] += 1
                if c3 == "CRITICAL":
                    result["check_correlations"]["check_3_critical"] += 1
                if c4 == "CRITICAL":
                    result["check_correlations"]["check_4_critical"] += 1

                # Verdicts by mode
                mode = record.get("mode") or "unknown"
                verdict = record.get("verdict") or "UNKNOWN"
                mode_bucket = result["verdicts_by_mode"].setdefault(
                    mode, {"CLEAN": 0, "WARNING": 0, "CRITICAL": 0}
                )
                mode_bucket[verdict] = mode_bucket.get(verdict, 0) + 1

                # Transformations
                for t in record.get("transformations", []) or []:
                    transformation_counts[t] = transformation_counts.get(t, 0) + 1
    except Exception:
        # Best-effort read; partial results are fine for a stats command.
        pass

    # Summarize deltas
    summarized = {}
    for k, values in delta_lists.items():
        if not values:
            summarized[k] = _empty_delta_summary()
            continue
        summarized[k] = {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "min": min(values),
            "max": max(values),
            "stddev": statistics.stdev(values) if len(values) >= 2 else 0.0,
        }
    result["metric_deltas"] = summarized

    # Transformations with percentage
    total = result["total_scans"]
    result["transformations"] = {
        name: {
            "count": count,
            "percentage": round(count / total * 100, 2) if total > 0 else 0.0,
        }
        for name, count in transformation_counts.items()
    }

    return result


def check_sharing_prompt() -> tuple:
    """
    Checks if a sharing prompt should be shown.
    Returns (should_prompt, count)
    """
    stats = get_stats()
    total = stats["total_scans"]
    
    if not (total % 100 == 0 and total > 0):
        return False, total
        
    status_path = os.path.join(get_ast_guard_dir(), "sharing_status.json")
    status = {"prompted_counts": [], "disabled": False}
    
    if os.path.exists(status_path):
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                status = json.load(f)
        except Exception:
            pass
            
    if status.get("disabled", False):
        return False, total
        
    if total in status.get("prompted_counts", []):
        return False, total
        
    # We should prompt! Update state to record this prompt
    status.setdefault("prompted_counts", []).append(total)
    try:
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status, f)
    except Exception:
        pass
        
    return True, total

def disable_sharing_prompt() -> None:
    status_path = os.path.join(get_ast_guard_dir(), "sharing_status.json")
    status = {"prompted_counts": [], "disabled": False}
    if os.path.exists(status_path):
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                status = json.load(f)
        except Exception:
            pass
    status["disabled"] = True
    try:
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status, f)
    except Exception:
        pass
