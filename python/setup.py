from pathlib import Path

from setuptools import setup

# Read the README.md for the long description
this_directory = Path(__file__).parent
readme_path = this_directory / "README.md"
if not readme_path.exists() and this_directory.parent.joinpath("README.md").exists():
    # The publish workflow copies README.md into this directory, while local
    # source installs use the repository-level README.
    readme_path = this_directory.parent / "README.md"
long_description = (
    readme_path.read_text(encoding="utf-8")
    if readme_path.exists()
    else "Caskada is a structured workflow runtime for Python and TypeScript."
)

setup(
    name="caskada",
    version="3.0.0",
    packages=["caskada", "caskada_logging"],
    package_data={"caskada": ["py.typed"], "caskada_logging": ["py.typed"]},
    author="Victor Duarte",
    description="Structured workflow runtime for Python and TypeScript.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://skada.ai/caskada/",
    license="MPL-2.0",
    python_requires=">=3.13",
    classifiers=[
        "Programming Language :: Python :: 3.13",
    ],
)
