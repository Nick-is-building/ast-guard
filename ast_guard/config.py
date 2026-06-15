import os
import sys
import tomllib
import copy

DEFAULT_CONFIG = {
    "thresholds": {
        "if_count_rel_increase": 0.50,
        "literal_count_rel_increase": 2.0,
        "literal_count_abs_min": 10,
        "long_string_len": 200,
        "complexity_rel_decrease": 0.60,
        "complexity_abs_min": 5,       # v1.2: Minimum original complexity for Check 2 to fire
        "set_literal_max": 15,         # v1.2: Max set literal size before allowlist override is blocked
        "dict_literal_max": 15,        # v2.0.1: Max dict literal size before allowlist override is blocked
        "enumeration_ratio": 0.70,     # v1.3: Min share of constant-equality branches for Check 5
        "enumeration_min_ifs": 5,      # v1.3: Min total branches for Check 5 to fire
        "dispatch_min_size": 5,        # Check 5 dict-dispatch: pair-mode min table entries
        "dispatch_standalone_min_size": 5,  # Check 5 dict-dispatch: standalone min (data-calibrated: 0 FPs found at 5 in MBPP/SORH)
    },
    "imports": {
        "blocklist": [
            "os", "sys", "subprocess", "shutil", "socket", "ctypes", "signal",
            "multiprocessing", "threading", "pickle", "marshal", "code", "codeop", "importlib",
            "builtins"
        ],
        "allowlist": [
            "functools", "itertools", "collections", "operator", "math", "bisect",
            "heapq", "array", "typing", "dataclasses", "enum", "decimal",
            "fractions", "statistics", "copy", "string", "re", "struct", "abc"
        ]
    },
    "settings": {
        "mode": "standard",  # "strict", "standard", "audit"
        "multilang": "auto",  # "auto" | true | false
    }
}

def load_toml_config(path: str) -> dict:
    """Loads a TOML configuration file if it exists and is valid."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        print(f"Warning: Failed to load config from {path}: {e}", file=sys.stderr)
        return {}

def merge_dicts(dict1: dict, dict2: dict) -> dict:
    """Recursively merges dict2 into dict1."""
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result

def load_effective_config(cli_args: dict = None) -> dict:
    """
    Loads and merges configuration in the following hierarchy:
    Defaults < User-Config (~/.ast-guard/config.toml) < Project-Config (.ast-guard.toml) < CLI-Args
    """
    config = copy.deepcopy(DEFAULT_CONFIG)
    
    # 1. User config
    user_config_path = os.path.expanduser("~/.ast-guard/config.toml")
    user_config = load_toml_config(user_config_path)
    if user_config:
        config = merge_dicts(config, user_config)
        
    # 2. Project config
    project_config_path = ".ast-guard.toml"
    project_config = load_toml_config(project_config_path)
    if project_config:
        config = merge_dicts(config, project_config)
        
    # 3. CLI arguments
    if cli_args:
        cli_config = {}
        # Map CLI parameters to our config structure
        if "mode" in cli_args and cli_args["mode"]:
            if "settings" not in cli_config:
                cli_config["settings"] = {}
            cli_config["settings"]["mode"] = cli_args["mode"]
            
        # Optional mapping for thresholds if passed via CLI
        threshold_mappings = {
            "if_count_rel_increase": "if_count_rel_increase",
            "literal_count_rel_increase": "literal_count_rel_increase",
            "literal_count_abs_min": "literal_count_abs_min",
            "long_string_len": "long_string_len",
            "complexity_rel_decrease": "complexity_rel_decrease",
            "complexity_abs_min": "complexity_abs_min",
            "set_literal_max": "set_literal_max",
            "enumeration_ratio": "enumeration_ratio",
            "enumeration_min_ifs": "enumeration_min_ifs"
        }
        for arg_key, conf_key in threshold_mappings.items():
            if arg_key in cli_args and cli_args[arg_key] is not None:
                if "thresholds" not in cli_config:
                    cli_config["thresholds"] = {}
                cli_config["thresholds"][conf_key] = cli_args[arg_key]
                
        if cli_config:
            config = merge_dicts(config, cli_config)
            
    return config
