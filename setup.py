from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="typomata",
    version="0.1.0",
    author="Florian Voit",
    description="A Python state machine library leveraging type hints",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/zpfvo/typomata",
    packages=find_packages(include=["typomata", "typomata.*"]),
    install_requires=["graphviz", 'dataclasses; python_version<"3.7"'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)
