import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from setuptools import setup, find_packages


class PyProjectParser:
    """
    A utility class to parse `pyproject.toml` files.

    Attributes:
        filepath (Path): Path to the pyproject.toml file.
        _content (Optional[str]): Cached file content.
    """

    def __init__(self, filepath: str = 'pyproject.toml'):
        """
        Initialize the parser with a file path.

        Args:
            filepath (str): Path to the `pyproject.toml` file.
        """
        self.filepath = Path(filepath)
        self._content: Optional[str] = None

    @property
    def content(self) -> str:
        """
        Lazily load the content of the pyproject.toml file.

        Returns:
            str: File content.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        if self._content is None:
            try:
                self._content = self.filepath.read_text(encoding='utf-8')
            except FileNotFoundError:
                raise FileNotFoundError(f"Could not find {self.filepath}")
        return self._content

    def get_section_content(self, section: str) -> str:
        """
        Extract the content of a specific section.

        Args:
            section (str): Section name (e.g., 'tool.poetry').

        Returns:
            str: Section content.

        Raises:
            ValueError: If the section is not found.
        """
        pattern = r'\[' + re.escape(section) + r'\](.*?)(?=\n\[|\Z)'
        match = re.search(pattern, self.content, re.DOTALL)

        if not match:
            raise ValueError(f"Could not find [{section}] section")

        return match.group(1)

    def get_value(self, section: str, key: str, default: Any = None) -> str:
        """
        Retrieve a specific key's value from a given section.

        Args:
            section (str): Section name.
            key (str): Key within the section.
            default (Any): Default value to return if not found.

        Returns:
            str: Retrieved value.

        Raises:
            ValueError: If the key or section is missing and no default is provided.
        """
        try:
            section_content = self.get_section_content(section)

            pattern = r'^\s*' + re.escape(key) + r'\s*=\s*(.*?)(?=^\s*\w+\s*=|\Z)'
            match = re.search(pattern, section_content, re.MULTILINE | re.DOTALL)

            if not match:
                if default is not None:
                    return default
                raise ValueError(f"Could not find key '{key}' in section [{section}]")

            return self._clean_value(match.group(1).strip())

        except Exception as e:
            if default is not None:
                return default
            raise ValueError(f"Error getting value for {key} in section {section}: {e}")

    def _clean_value(self, value: str) -> str:
        """
        Remove surrounding quotes from simple TOML string values.

        Args:
            value (str): Input string.

        Returns:
            str: Unquoted string.
        """
        value = value.strip()
        if ((value.startswith('"') and value.endswith('"') and value.count('"') == 2) or
                (value.startswith("'") and value.endswith("'") and value.count("'") == 2)):
            return value[1:-1]
        return value


class TomlArrayParser:
    """
    Utility to parse TOML array strings into Python lists.
    """

    @staticmethod
    def parse(value: str) -> List[str]:
        """
        Parse a TOML array string into a Python list.

        Args:
            value (str): TOML-formatted array (e.g., '["a", "b"]').

        Returns:
            List[str]: List of string elements.
        """
        if not value or not value.strip():
            return []

        # Handle multiline arrays
        value = re.sub(r'\s+', ' ', value).strip()

        # Handle non-array values
        if not (value.startswith('[') and value.endswith(']')):
            return TomlArrayParser._parse_single_value(value)

        # Parse array content
        content = value[1:-1].strip()
        if not content:
            return []

        return TomlArrayParser._parse_array_content(content)

    @staticmethod
    def _parse_single_value(value: str) -> List[str]:
        """
        Handle and parse a single string value.

        Args:
            value (str): A string without brackets.

        Returns:
            List[str]: Single-item list.
        """
        cleaned = TomlArrayParser._remove_quotes(value)
        return [cleaned] if cleaned else []

    @staticmethod
    def _parse_array_content(content: str) -> List[str]:
        """
        Parse the inside of a TOML array (without brackets).

        Args:
            content (str): Raw string inside the brackets.

        Returns:
            List[str]: List of parsed strings.
        """
        items = []
        current_item = ""
        in_quotes = False
        quote_char = None

        for i, char in enumerate(content):
            if char in ['"', "'"] and (i == 0 or content[i - 1] != '\\'):
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None
                else:
                    current_item += char
            elif char == ',' and not in_quotes:
                item = TomlArrayParser._remove_quotes(current_item.strip())
                if item:
                    items.append(item)
                current_item = ""
            else:
                if not (char in ['"', "'"] and in_quotes):
                    current_item += char

        # Add the last item
        if current_item.strip():
            item = TomlArrayParser._remove_quotes(current_item.strip())
            if item:
                items.append(item)

        return items

    @staticmethod
    def _remove_quotes(value: str) -> str:
        """
        Strip quotes from around a string value.

        Args:
            value (str): Input string.

        Returns:
            str: Unquoted string.
        """
        value = value.strip()
        if ((value.startswith('"') and value.endswith('"')) or
                (value.startswith("'") and value.endswith("'"))):
            return value[1:-1]
        return value


class RequirementsReader:
    """
    Utility to read dependencies from a `requirements.txt` file.
    """

    @staticmethod
    def read(filepath: str = 'requirements.txt') -> List[str]:
        """
        Parse dependencies from a requirements.txt file.

        Args:
            filepath (str): Path to the requirements file.

        Returns:
            List[str]: List of dependency strings.

        Raises:
            FileNotFoundError: If the file is not found.
        """
        try:
            path = Path(filepath)
            content = path.read_text(encoding='utf-8')

            requirements = []
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('--') and not line.startswith('#'):
                    # Remove comments and line continuations
                    req = line.split(';')[0].rstrip('\\').strip()
                    if req:
                        requirements.append(req)

            return requirements
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Could not find {filepath}: {e}")


class AuthorParser:
    """
    Parses author information from the pyproject.toml file.

    Attributes:
        parser (PyProjectParser): An instance of PyProjectParser.
    """

    def __init__(self, parser: PyProjectParser):
        self.parser = parser

    def parse(self) -> Tuple[str, str]:
        """
        Parse authors from the `tool.poetry.authors` section.

        Returns:
            Tuple[str, str]: Author names and emails as comma-separated strings.

        Raises:
            ValueError: If parsing fails.
        """
        try:
            authors_raw = self.parser.get_value("tool.poetry", "authors")
            authors_list = TomlArrayParser.parse(authors_raw)

            names = []
            emails = []

            for author_entry in authors_list:
                name, email = self._parse_author_entry(author_entry)
                if name:
                    names.append(name)
                if email:
                    emails.append(email)

            return ', '.join(names), ', '.join(emails)

        except Exception as e:
            raise ValueError(f"Error parsing authors: {e}")

    @staticmethod
    def _parse_author_entry(entry: str) -> Tuple[str, str]:
        """
        Parse a single author entry like "Name <email@example.com>".

        Args:
            entry (str): Raw author string.

        Returns:
            Tuple[str, str]: (Name, Email)
        """
        if '<' in entry and '>' in entry:
            name = entry.split('<')[0].strip()
            email_match = re.search(r'<([^>]+)>', entry)
            email = email_match.group(1).strip() if email_match else ""
            return name, email
        return entry.strip(), ""


class ExtrasParser:
    """
    Parses extras from the `[tool.poetry.extras]` section.
    """

    def __init__(self, parser: PyProjectParser):
        """
         Initialize with a PyProjectParser.

         Args:
             parser (PyProjectParser): Parser instance.
         """
        self.parser = parser

    def parse(self) -> Dict[str, List[str]]:
        """
        Parse extras from the pyproject.toml file.

        Returns:
            Dict[str, List[str]]: A mapping of extra name to list of dependencies.

        Raises:
            ValueError: If parsing fails.
        """
        try:
            extras_section = self.parser.get_section_content("tool.poetry.extras")
            extras = {}

            for line in extras_section.split('\n'):
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    if value.startswith('[') and value.endswith(']'):
                        items = value[1:-1].replace('"', '').replace("'", "")
                        extras[key] = [item.strip() for item in items.split(',') if item.strip()]

            return extras
        except Exception as e:
            raise ValueError(f"Error parsing extras: {e}")


class SetupConfigBuilder:
    """
    Builds the `setup.py` configuration from pyproject.toml.

    Attributes:
        parser (PyProjectParser): TOML file parser.
        author_parser (AuthorParser): Author section parser.
        extras_parser (ExtrasParser): Extras section parser.
    """

    def __init__(self, pyproject_path: str = 'pyproject.toml'):
        """
        Initialize the builder with the path to `pyproject.toml`.

        Args:
            pyproject_path (str): Path to pyproject.toml file.
        """
        self.parser = PyProjectParser(pyproject_path)
        self.author_parser = AuthorParser(self.parser)
        self.extras_parser = ExtrasParser(self.parser)

    def build_config(self) -> Dict[str, Any]:
        """
        Construct a dictionary suitable for passing to `setuptools.setup()`.

        Returns:
            Dict[str, Any]: Setup configuration dictionary.

        Raises:
            ValueError: If required fields or files are missing.
        """
        config = {}

        # Basic project info
        config['name'] = self.parser.get_value("tool.poetry", "name")
        config['version'] = self.parser.get_value("tool.poetry", "version")
        config['description'] = self.parser.get_value("tool.poetry", "description")
        config['url'] = self.parser.get_value("tool.poetry", "homepage", "")
        config['license'] = self.parser.get_value("tool.poetry", "license", "")

        # Authors
        authors, emails = self.author_parser.parse()
        config['author'] = authors
        config['author_email'] = emails

        # Arrays
        config['classifiers'] = TomlArrayParser.parse(
            self.parser.get_value("tool.poetry", "classifiers", "")
        )
        config['keywords'] = TomlArrayParser.parse(
            self.parser.get_value("tool.poetry", "keywords", "")
        )

        # Dependencies
        config['install_requires'] = RequirementsReader.read()
        config['extras_require'] = self.extras_parser.parse()

        # Package info
        config['python_requires'] = self.parser.get_value("tool.poetry.dependencies", "python", "")

        # Long description
        readme_path = self.parser.get_value("tool.poetry", "readme", "")
        config['long_description'] = self._read_long_description(readme_path)
        config['long_description_content_type'] = "text/markdown"

        # Packages
        packages_info = self._parse_packages()
        config.update(packages_info)

        # Entry points
        config['entry_points'] = self._parse_entry_points()

        # Scripts (specific to jpipe-runner)
        if config['name'] == "jpipe-runner":
            config['scripts'] = ['bin/jpipe-runner']

        config['include_package_data'] = True

        return config

    @staticmethod
    def _read_long_description(readme_path: str) -> str:
        """
        Read the project's long description from a README file.

        Args:
            readme_path (str): Path to README file.

        Returns:
            str: Content of the README.

        Raises:
            ValueError: If file cannot be read.
        """
        if not readme_path:
            raise ValueError("No readme file specified in pyproject.toml")

        readme_path = readme_path.strip().strip('"').strip("'")

        try:
            return Path(readme_path).read_text(encoding='utf-8')
        except Exception as e:
            raise ValueError(f"Error reading long description from {readme_path}: {e}")

    def _parse_packages(self) -> Dict[str, Any]:
        """
        Parse the `packages` configuration from pyproject.toml.

        Returns:
            Dict[str, Any]: Package info including `packages` and `package_dir`.
        """
        packages_raw = self.parser.get_value("tool.poetry", "packages", "")
        packages_match = re.search(r'from\s*=\s*"([^"]+)"', packages_raw)

        if packages_match:
            packages_from = packages_match.group(1)
            return {
                'packages': find_packages(where=packages_from),
                'package_dir': {"": packages_from}
            }

        return {'packages': find_packages()}

    def _parse_entry_points(self) -> Dict[str, List[str]]:
        """
        Parse entry points for the `console_scripts`.

        Returns:
            Dict[str, List[str]]: Entry points dictionary.
        """
        try:
            name = self.parser.get_value("tool.poetry", "name")
            entrypoint = self.parser.get_value("tool.poetry.scripts", "jpipe-runner", "")

            if entrypoint:
                return {
                    "console_scripts": [f"{name} = {entrypoint}"]
                }
        except Exception as e:
            raise ValueError(f"Error parsing entry points: {e}")

        return {}

    @staticmethod
    def print_config(config: Dict[str, Any]) -> None:
        """
        Pretty print the setup configuration.

        Args:
            config (Dict[str, Any]): The setup configuration dictionary.
        """
        print("=== Setup.py Configuration Values ===")
        for key, value in config.items():
            print(f"{key.replace('_', ' ').title()}: {value}")
        print("=====================================")


if __name__ == "__main__":
    builder = SetupConfigBuilder()
    config = builder.build_config()
    if len(sys.argv) > 1 and sys.argv[1] == '--print-config':
        builder.print_config(config)

    setup(**config)
