from setuptools import setup, find_packages

# Metadata and dependencies are specified in setup.cfg and pyproject.toml
setup(
    packages=find_packages(include=['aiblock', 'aiblock.*']),
    package_data={
        "aiblock": ["py.typed"],
    },
) 