from setuptools import setup, find_packages

# Metadata and dependencies are specified in setup.cfg and pyproject.toml
setup(
    packages=find_packages(include=['lineage', 'lineage.*']),
    package_data={
        "lineage": ["py.typed"],
    },
) 