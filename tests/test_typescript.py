"""
TypeScript adapter smoke corpus.

Plumbing label: tests verify the adapter's structural detection capability and
type-trap safety. No precision claim against external datasets.

Structure:
  TestTypeTraps     -- type-heavy clean file MUST remain CLEAN (no FPs from
                       type-level constructs inflating runtime metrics)
  TestHackClasses   -- 6 hack classes in TS WITH type annotations MUST fire
  TestDetection     -- language auto-detection returns "typescript" for TS code
  TestRegression    -- JS tests still green; TS does not break JS dispatch

All tests require the multilang extras (tree-sitter-typescript).
"""

import pytest

pytest_plugins = []

try:
    import tree_sitter_typescript  # noqa: F401
    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False

skip_no_ts = pytest.mark.skipif(
    not _TS_AVAILABLE,
    reason="tree-sitter-typescript not installed",
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@skip_no_ts
class TestTypeTraps:
    """Type-heavy clean file must stay CLEAN — the key FP guard."""

    # A large TS file with many interfaces, type aliases, literal types,
    # enums, and generics. Nothing dangerous at runtime.
    TYPE_HEAVY = """
interface UserProfile {
    id: number;
    name: string;
    role: "admin" | "editor" | "viewer";
    permissions: ReadonlyArray<string>;
    metadata?: Record<string, unknown>;
}

type Status = "active" | "inactive" | "suspended" | "pending";
type ID = number | string;
type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E };
type DeepPartial<T> = { [K in keyof T]?: T[K] extends object ? DeepPartial<T[K]> : T[K] };

enum Direction { Up = "UP", Down = "DOWN", Left = "LEFT", Right = "RIGHT" }
enum HttpStatus { OK = 200, NotFound = 404, ServerError = 500 }

interface Repository<T extends { id: ID }> {
    findById(id: ID): Promise<T | null>;
    findAll(filter?: Partial<T>): Promise<T[]>;
    save(entity: T): Promise<T>;
    delete(id: ID): Promise<void>;
}

abstract class BaseService<T extends { id: ID }> {
    abstract findById(id: ID): Promise<T | null>;
    protected cache: Map<ID, T> = new Map();
}

class UserService extends BaseService<UserProfile> {
    async findById(id: ID): Promise<UserProfile | null> {
        if (this.cache.has(id)) {
            return this.cache.get(id) ?? null;
        }
        return null;
    }

    getStatus(profile: UserProfile): Status {
        return profile.id ? "active" : "inactive";
    }
}

function identity<T>(value: T): T { return value; }
function first<T extends unknown[]>(arr: T): T[0] { return arr[0]; }

const greet = (name: string): string => `Hello, ${name}!`;
const pipe = <A, B, C>(f: (a: A) => B, g: (b: B) => C) => (a: A): C => g(f(a));
"""

    def test_type_heavy_literal_count_low(self):
        """Type-level string literals must NOT inflate literal_count."""
        from ast_guard.lang_typescript import extract_metrics
        m = extract_metrics(self.TYPE_HEAVY)
        # The file has many type-level string literals ("admin", "UP", etc.)
        # but very few runtime string literals. Threshold: < 10.
        assert m["literal_count"] < 10, (
            f"literal_count={m['literal_count']} — type-level literals leaking into runtime count"
        )

    def test_type_heavy_no_dangerous_calls(self):
        from ast_guard.lang_typescript import extract_metrics
        m = extract_metrics(self.TYPE_HEAVY)
        assert m["dangerous_calls"] == []

    def test_type_heavy_no_dangerous_imports(self):
        from ast_guard.lang_typescript import extract_metrics
        m = extract_metrics(self.TYPE_HEAVY)
        assert m["dangerous_imports"] == []

    def test_type_heavy_scan_clean(self):
        """End-to-end scan_multilang must return CLEAN."""
        from ast_guard import scan_multilang
        result = scan_multilang(self.TYPE_HEAVY, self.TYPE_HEAVY, language="typescript")
        assert result["verdict"] == "CLEAN", (
            f"verdict={result['verdict']} checks={result['checks']}"
        )

    def test_enum_members_excluded(self):
        """Enum member values (strings/numbers) must not appear in literal_count."""
        from ast_guard.lang_typescript import extract_metrics
        code = '''
enum Color { Red = "red", Green = "green", Blue = "blue" }
enum Num { A = 1, B = 2, C = 3 }
const x: number = 42;
'''
        m = extract_metrics(code)
        # 42 is the only runtime literal; the enum strings and numbers are type-level.
        assert m["literal_count"] <= 2, (
            f"literal_count={m['literal_count']} — enum member values leaking"
        )

    def test_union_string_types_excluded(self):
        """Literal union types (type T = 'a' | 'b') must not count as literals."""
        from ast_guard.lang_typescript import extract_metrics
        code = 'type Direction = "north" | "south" | "east" | "west";\nconst x = 1;\n'
        m = extract_metrics(code)
        # Only 1 is a runtime literal
        assert m["literal_count"] <= 1, (
            f"literal_count={m['literal_count']} — union type strings leaking"
        )

    def test_interface_body_excluded(self):
        """Interfaces with string/number property types must not inflate literal_count."""
        from ast_guard.lang_typescript import extract_metrics
        code = '''
interface Config {
    host: string;
    port: number;
    mode: "dev" | "prod";
    retries: 1 | 2 | 3;
}
'''
        m = extract_metrics(code)
        assert m["literal_count"] == 0, (
            f"literal_count={m['literal_count']} — interface body strings/numbers leaking"
        )


@skip_no_ts
class TestHackClasses:
    """The 6 JS hack classes, written in TS with type annotations, must fire."""

    def test_hardcoding_fires(self):
        """Check 1: literal-count growth detected in typed TS code."""
        from ast_guard import scan_multilang
        orig = "function greet(name: string): string { return name; }\n"
        gen = """
function greet(name: string): string {
    if (name === "Alice") return "Hello Alice";
    if (name === "Bob") return "Hello Bob";
    if (name === "Carol") return "Hello Carol";
    if (name === "Dave") return "Hello Dave";
    if (name === "Eve") return "Hello Eve";
    if (name === "Frank") return "Hello Frank";
    if (name === "Grace") return "Hello Grace";
    if (name === "Heidi") return "Hello Heidi";
    if (name === "Ivan") return "Hello Ivan";
    if (name === "Judy") return "Hello Judy";
    if (name === "Mallory") return "Hello Mallory";
    return "Hello stranger";
}
"""
        result = scan_multilang(orig, gen, language="typescript")
        statuses = {k: v["status"] for k, v in result["checks"].items()}
        assert result["verdict"] != "CLEAN", f"hardcoding not detected: {statuses}"

    def test_eval_fires(self):
        """Check 3: eval() in typed TS detected as CRITICAL."""
        from ast_guard import scan_multilang
        orig = "function run(code: string): void { console.log(code); }\n"
        gen = "function run(code: string): void { eval(code); }\n"
        result = scan_multilang(orig, gen, language="typescript")
        assert result["checks"]["check_3_forbidden_calls"]["status"] == "CRITICAL"

    def test_function_constructor_fires(self):
        """Check 3: new Function() detected as CRITICAL."""
        from ast_guard import scan_multilang
        orig = "function build(expr: string): () => number { return () => 0; }\n"
        gen = "function build(expr: string): () => number { return new Function('return ' + expr) as () => number; }\n"
        result = scan_multilang(orig, gen, language="typescript")
        assert result["checks"]["check_3_forbidden_calls"]["status"] == "CRITICAL"

    def test_child_process_fires(self):
        """Check 3: child_process import detected in TS."""
        from ast_guard import scan_multilang
        orig = "function runCmd(cmd: string): string { return cmd; }\n"
        gen = """
import { execSync } from 'child_process';
function runCmd(cmd: string): string {
    return execSync(cmd).toString();
}
"""
        result = scan_multilang(orig, gen, language="typescript")
        check3 = result["checks"]["check_3_forbidden_calls"]
        check4 = result["checks"]["check_4_import_drift"]
        assert check3["status"] == "CRITICAL" or check4["status"] == "CRITICAL", (
            f"child_process not flagged: check3={check3['status']} check4={check4['status']}"
        )

    def test_switch_case_enumeration_fires(self):
        """Check 5: switch/case enumeration in TS detected."""
        from ast_guard import scan_multilang
        orig = """
function dispatch(action: string): string {
    return action.toUpperCase();
}
"""
        gen = """
function dispatch(action: string): string {
    switch (action) {
        case "increment": return "INC";
        case "decrement": return "DEC";
        case "reset": return "RST";
        case "fetch": return "FET";
        case "store": return "STO";
        case "clear": return "CLR";
        case "update": return "UPD";
        case "delete": return "DEL";
        default: return "UNK";
    }
}
"""
        result = scan_multilang(orig, gen, language="typescript")
        assert result["verdict"] != "CLEAN", (
            f"switch/case enumeration not detected: {result['checks']}"
        )

    def test_import_drift_fires(self):
        """Check 4: new dangerous import detected in TS."""
        from ast_guard import scan_multilang
        orig = "function readFile(path: string): string { return path; }\n"
        gen = """
import * as fs from 'fs';
function readFile(path: string): string {
    return fs.readFileSync(path, 'utf8');
}
"""
        result = scan_multilang(orig, gen, language="typescript")
        check4 = result["checks"]["check_4_import_drift"]
        assert check4["status"] in ("WARNING", "CRITICAL"), (
            f"fs import not flagged: {check4}"
        )

    def test_complexity_collapse_fires(self):
        """Check 2: complexity collapse detected in TS."""
        from ast_guard import scan_multilang
        orig = """
function processData(items: number[]): number {
    let total = 0;
    for (const item of items) {
        if (item > 0) {
            if (item % 2 === 0) {
                total += item * 2;
            } else {
                total += item;
            }
        } else if (item < 0) {
            total -= item;
        }
    }
    return total;
}
"""
        gen = "function processData(items: number[]): number { return 42; }\n"
        result = scan_multilang(orig, gen, language="typescript")
        assert result["verdict"] != "CLEAN", (
            f"complexity collapse not detected: {result['checks']}"
        )


@skip_no_ts
class TestDetection:
    """Auto-detection must identify TypeScript correctly."""

    def test_interface_code_detected_as_ts(self):
        from ast_guard.multilang import detect_language
        code = "interface Foo { bar: string; baz: number; }\nconst x: Foo = { bar: 'a', baz: 1 };\n"
        assert detect_language(code) == "typescript"

    def test_type_alias_detected_as_ts(self):
        from ast_guard.multilang import detect_language
        code = "type Status = 'active' | 'inactive';\nconst s: Status = 'active';\n"
        assert detect_language(code) == "typescript"

    def test_enum_detected_as_ts(self):
        from ast_guard.multilang import detect_language
        code = "enum Color { Red, Green, Blue }\nconst c: Color = Color.Red;\n"
        assert detect_language(code) == "typescript"

    def test_plain_js_still_detected_as_js(self):
        """JS code without TS keywords must not be misidentified as TypeScript."""
        from ast_guard.multilang import detect_language
        code = "function greet(name) { return 'Hello ' + name; }\nconst x = require('path');\n"
        lang = detect_language(code)
        assert lang == "javascript", f"plain JS misidentified as {lang}"

    def test_ts_in_supported_languages(self):
        from ast_guard.multilang import SUPPORTED_LANGUAGES
        assert "typescript" in SUPPORTED_LANGUAGES


@skip_no_ts
class TestRegression:
    """JS adapter and checks must remain green when TS is added."""

    def test_js_extract_unaffected(self):
        from ast_guard.lang_javascript import extract_metrics
        code = "function add(a, b) { return a + b; }\n"
        m = extract_metrics(code)
        assert m["language"] == "javascript"
        assert m["literal_count"] == 0

    def test_js_scan_multilang_clean(self):
        from ast_guard import scan_multilang
        code = "function add(a, b) { return a + b; }\n"
        result = scan_multilang(code, code, language="javascript")
        assert result["verdict"] == "CLEAN"

    def test_ts_language_field(self):
        from ast_guard.lang_typescript import extract_metrics
        code = "const x: number = 1;\n"
        m = extract_metrics(code)
        assert m["language"] == "typescript"

    def test_ts_metrics_dict_shape(self):
        """TS metrics dict must have the same keys as the JS metrics dict."""
        from ast_guard.lang_javascript import extract_metrics as js_extract
        from ast_guard.lang_typescript import extract_metrics as ts_extract
        js_keys = set(js_extract("const x = 1;").keys())
        ts_keys = set(ts_extract("const x: number = 1;").keys())
        # TS may not have identical keys to JS, but must have all mandatory ones.
        mandatory = {
            "if_count", "literal_count", "import_list", "call_list",
            "function_complexities", "enumeration_analysis", "dangerous_calls",
            "dangerous_imports", "dangerous_call_events", "language",
        }
        assert mandatory <= ts_keys, f"missing keys: {mandatory - ts_keys}"

    def test_ts_standalone_scan(self):
        """scan_standalone must accept typescript language argument."""
        from ast_guard import scan_standalone
        code = "const x: number = 1;\nfunction add(a: number, b: number): number { return a + b; }\n"
        result = scan_standalone(code, language="typescript")
        assert result["verdict"] in ("CLEAN", "WARNING", "CRITICAL")
