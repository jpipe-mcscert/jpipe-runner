from setuptools import setup, find_packages

def read_requirements(path):
    with open(path, 'r', encoding='utf-8') as f:
        return [line.split(';')[0].rstrip('\\').strip()
                for line in f
                if line.strip() and not line.lstrip().startswith('--')]

install_requires = read_requirements('requirements.txt')

setup(
    name="jpipe-runner",
    version="2.0.0b12",
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
    python_requires=">=3.11",
    install_requires=install_requires,
    entry_points={
        "console_scripts": [
            "jpipe-runner = jpipe_runner.runner:main"
        ]
    },
    scripts=['bin/jpipe-runner'],
)
