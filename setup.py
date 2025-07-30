import re

from setuptools import setup, find_packages


def read_requirements(path='requirements.txt'):
    with open(path, 'r', encoding='utf-8') as f:
        return [line.split(';')[0].rstrip('\\').strip()
                for line in f
                if line.strip() and not line.lstrip().startswith('--')]


def read_pyproject_extras():
    """Parse extras from pyproject.toml using only native Python"""
    with open('pyproject.toml', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the [tool.poetry.extras] section
    extras_pattern = r'\[tool\.poetry\.extras\](.*?)(?=\n\[|\Z)'
    match = re.search(extras_pattern, content, re.DOTALL)

    if not match:
        return {}

    extras_section = match.group(1)
    extras = {}

    # Parse each line in the extras section
    for line in extras_section.split('\n'):
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()

            # Parse the list format: ["package1", "package2"]
            if value.startswith('[') and value.endswith(']'):
                # Remove brackets and split by comma
                items = value[1:-1].replace('"', '').replace("'", "")
                extras[key] = [item.strip() for item in items.split(',') if item.strip()]

    return extras


def read_pyproject_version():
    """Parse version from pyproject.toml using only native Python"""
    with open('pyproject.toml', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the [tool.poetry] section
    poetry_pattern = r'\[tool\.poetry\](.*?)(?=\n\[|\Z)'
    match = re.search(poetry_pattern, content, re.DOTALL)

    if not match:
        raise ValueError("Could not find [tool.poetry] section in pyproject.toml")

    poetry_section = match.group(1)

    # Look for version line in the poetry section
    for line in poetry_section.split('\n'):
        line = line.strip()
        if line.startswith('version') and '=' in line:
            _, value = line.split('=', 1)
            value = value.strip()
            # Remove quotes
            if (value.startswith('"') and value.endswith('"')) or \
                    (value.startswith("'") and value.endswith("'")):
                return value[1:-1]
            return value

    raise ValueError("Could not find version in [tool.poetry] section")


install_requires = read_requirements()
extras_require = read_pyproject_extras()
version = read_pyproject_version()

setup(
    name="jpipe-runner",
    version=version,
    description="A Justification Runner designed for jPipe.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Jason Lyu, Sébastien Mosser, Baptiste Lacroix",
    author_email="xjasonlyu@gmail.com, mossers@mcmaster.ca, baptiste.lacroix03@gmail.com",
    url="https://github.com/jpipe-mcscert/jpipe-runner",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    keywords=["justification", "pipeline", "ML", "AI"],
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=install_requires,
    extras_require=extras_require,
    entry_points={
        "console_scripts": [
            "jpipe-runner = jpipe_runner.runner:main"
        ]
    },
    scripts=['bin/jpipe-runner'],
)
