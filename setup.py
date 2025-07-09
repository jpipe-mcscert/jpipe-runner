from setuptools import setup, find_packages

setup(
    name="jpipe-runner",
    version="2.0.0",
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
    install_requires=[
        "networkx>=3.4.2,<4.0.0",
        "termcolor>=2.5.0,<3.0.0",
        "pygraphviz>=1.11,<2.0.0",
        "matplotlib>=3.10.3,<4.0.0",
        "pyyaml>=6.0.2,<7.0.0",
    ],
    entry_points={
        "console_scripts": [
            "jpipe-runner = jpipe_runner.runner:main"
        ]
    },
    scripts=['bin/jpipe-runner'],
)
