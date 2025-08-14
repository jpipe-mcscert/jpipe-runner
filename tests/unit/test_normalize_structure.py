import unittest

import yaml

from jpipe_runner.utils import parse_value, normalize_structure


class TestRuntimeContext(unittest.TestCase):
    def test_parse_value_basic(self):
        test_cases = [
            # --- Simple booleans ---
            ("true", True),
            ("True", True),
            ("false", False),
            ("False", False),
            (" TRUE ", True),
            (" FALSE ", False),

            # --- None / Null ---
            ("none", None),
            ("None", None),
            ("null", None),
            (" NULL ", None),

            # --- Integers ---
            ("0", 0),
            ("42", 42),
            ("-10", -10),
            ("+5", 5),

            # --- Floats ---
            ("3.14", 3.14),
            ("-2.5", -2.5),
            ("+0.5", 0.5),

            # --- Strings with quotes ---
            ('"hello"', "hello"),
            ("'world'", "world"),

            # --- Strings without quotes ---
            ("hello", "hello"),
            ("123abc", "123abc"),

            # --- Already parsed Python types ---
            (True, True),
            (False, False),
            (None, None),
            (42, 42),
            (3.14, 3.14),

            # --- Lists ---
            ('[1, 2, 3]', [1, 2, 3]),
            ('["a", "b", "c"]', ["a", "b", "c"]),
            ("[true, false, null]", [True, False, None]),
            ("[{'a': 1}, {'b': 2}]", [{"a": 1}, {"b": 2}]),

            # -- Dicts--
            ('{"key": "value", "flag": true}', {"key": "value", "flag": True}),
            ("{'x': 1, 'y': None}", {"x": 1, "y": None}),
            ('{"nested": [1, 2, 3]}', {"nested": [1, 2, 3]}),
            # Dict with mixed types (string, int, bool, None, float)
            ("{'str': 'text', 'int': 42, 'bool': true, 'none': null, 'float': 3.14}",
             {"str": "text", "int": 42, "bool": True, "none": None, "float": 3.14}),

            # --- Nested complex ---
            ('[{"a": [1, 2]}, {"b": {"c": "d"}}]', [{"a": [1, 2]}, {"b": {"c": "d"}}]),
        ]
        for input_val, expected in test_cases:
            with self.subTest(input_val=input_val):
                self.assertEqual(parse_value(input_val), expected)

    def test_normalize_structure_simple_dict(self):
        data = {
            "a": "true",
            "b": "42",
            "c": "3.14",
            "d": "none",
            "e": '"text"',
        }
        expected = {
            "a": True,
            "b": 42,
            "c": 3.14,
            "d": None,
            "e": "text",
        }
        self.assertEqual(normalize_structure(data), expected)

    def test_normalize_structure_list(self):
        data = ["1", "false", "None", "hello", '"quoted"']
        expected = [1, False, None, "hello", "quoted"]
        self.assertEqual(normalize_structure(data), expected)

    def test_normalize_structure_nested(self):
        data = {
            "numbers": ["1", "2", "3.14", "none"],
            "flags": {"is_valid": "true", "is_empty": "false"},
            "nested": [{"x": "10"}, {"y": '"hello"'}]
        }
        expected = {
            "numbers": [1, 2, 3.14, None],
            "flags": {"is_valid": True, "is_empty": False},
            "nested": [{"x": 10}, {"y": "hello"}]
        }
        self.assertEqual(normalize_structure(data), expected)

    def test_normalize_structure_mixed_types(self):
        data = {
            "already_int": 5,
            "already_bool": True,
            "already_none": None,
            "stringy_number": "007",
            "stringy_float": "0003.1400"
        }
        expected = {
            "already_int": 5,
            "already_bool": True,
            "already_none": None,
            "stringy_number": 7,
            "stringy_float": 3.14
        }
        self.assertEqual(normalize_structure(data), expected)

    @staticmethod
    def load_yaml_file(filename):
        path = f"tests/unit/resources/input_normalisation/{filename}"
        with open(path, "r") as f:
            return yaml.safe_load(f)

    def test_config_simple(self):
        data = self.load_yaml_file("config_simple.yaml")
        normalized = normalize_structure(data)
        self.assertEqual(normalized, {
            "bool_true": True,
            "bool_false": False,
            "none_val": None,
            "int_val": 42,
            "float_val": 3.14,
            "string_val": "hello",
            "quoted_string": "hello world",
        })

    def test_config_complex(self):
        data = self.load_yaml_file("config_complex.yaml")
        normalized = normalize_structure(data)
        self.assertEqual(normalized, {
            "pipeline": {
                "input_data": [1, 2, 3, None, 4, 5],
                "steps": [
                    {"name": "step1", "enabled": True, "retries": 3},
                    {"name": "step2", "enabled": False, "retries": 0}
                ],
                "metadata": {
                    "version": 1.0,
                    "tags": ["alpha", "beta", 42, None],
                    "params": {
                        "threshold": 0.75,
                        "max_items": 100,
                        "debug_mode": True
                    }
                },
                "settings": {
                    "numbers": [1, 2, 3],
                    "options": {"key": "value", "flag": True}
                },
                "nested_list": [{"a": 1}, {"b": 2}]
            }
        })

    def test_config_mixed(self):
        data = self.load_yaml_file("config_mixed.yaml")
        normalized = normalize_structure(data)
        self.assertEqual(normalized, {
            "already_int": 5,
            "already_bool": True,
            "already_none": None,
            "stringy_number": 7,
            "stringy_float": 3.14
        })

    def test_config_nested(self):
        data = self.load_yaml_file("config_nested.yaml")
        normalized = normalize_structure(data)
        self.assertEqual(normalized, {
            "numbers": [1, 2, 3.14, None],
            "flags": {"is_valid": True, "is_empty": False},
            "nested": [{"x": 10}, {"y": "hello"}]
        })

    def test_config_list(self):
        data = self.load_yaml_file("config_list.yaml")
        normalized = normalize_structure(data)
        self.assertEqual(normalized, {
            "items": [1, 2, 3.14, None, True, False, "quoted"]
        })
